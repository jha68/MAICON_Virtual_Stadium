import asyncio
import hmac
from fastapi import APIRouter, Request, HTTPException
from .errors import invalid


def admin_router(service):
    router=APIRouter(prefix="/admin")
    def authorized(request):
        header=request.headers.get("authorization","")
        if not hmac.compare_digest(header,"Bearer "+service.admin_token):
            raise HTTPException(401,"administrator authentication required")
        if request.client and request.client.host not in ("127.0.0.1","::1","testclient"):
            raise HTTPException(403,"administrator API is loopback-only")

    def install_backend(engine,requested):
        if service.gateway is None:
            return
        gateway=service.gateway
        current="3d" if gateway.capabilities.get("rgb") else "2d"
        if current==requested and gateway.config is engine.config:
            return
        if current==requested:
            gateway.reconfigure(engine.config)
        elif requested=="3d":
            from maicon_sim.backends.bullet.render_worker import AsyncBulletBackend
            gateway.reconfigure(engine.config,AsyncBulletBackend(engine.config))
        else:
            from maicon_sim.backends.two_d import TwoDBackend
            gateway.reconfigure(engine.config,TwoDBackend(engine.config))

    def simple(kind):
        async def handler(request:Request):
            authorized(request)
            engine=service.select_engine(request.query_params.get("session")=="rehearsal")
            other=service.engine if engine is service.rehearsal_engine else service.rehearsal_engine
            if kind in ("enter_ready","start") and other is not None and other.phase not in ("idle","finished","waiting"):
                raise HTTPException(409,"physical robot set is already assigned to another session")
            result=await service.submit(kind,engine=engine)
            return result if isinstance(result,dict) else {"accepted":True}
        return handler
    for path,kind in (("ready-phase","enter_ready"),("start","start"),("pause","pause"),
                      ("resume","resume"),("finish","finish")):
        router.add_api_route("/"+path,simple(kind),methods=["POST"])

    @router.get("/snapshot")
    async def snapshot(request:Request):
        authorized(request)
        return await service.submit("snapshot",engine=service.select_engine(request.query_params.get("session")=="rehearsal"))

    @router.get("/result")
    async def result(request:Request):
        authorized(request)
        engine=service.select_engine(request.query_params.get("session")=="rehearsal")
        if engine.phase!="finished":
            raise HTTPException(409,"match has not finished")
        return await service.submit("result",engine=engine)

    @router.post("/configure")
    async def configure(request:Request):
        authorized(request)
        body=await service.body(request,{"scenario_path","backend","clock_mode","session","test_mode"})
        from maicon_sim.config.loader import validate_schema
        try:
            validate_schema(body,"admin_configure","admin configure")
        except ValueError:
            invalid("configure","request does not match the admin configure contract")
        if "test_mode" in body and type(body["test_mode"]) is not bool:
            invalid("test_mode","test_mode must be a boolean")
        if body.get("clock_mode","realtime")!="realtime":
            invalid("clock_mode","HTTP services require realtime clock mode")
        if body.get("session","report") not in ("report","rehearsal"):
            invalid("session","session must be report or rehearsal")
        for engine in (service.engine,service.rehearsal_engine):
            if engine is not None and engine.phase not in ("idle","finished"):
                raise HTTPException(409,"an active robot set cannot be reconfigured")
        from maicon_sim.config.loader import load_scenario
        try:
            config=load_scenario(body["scenario_path"],backend=body.get("backend"))
        except (KeyError,ValueError) as error:
            invalid("scenario_path",str(error))
        requested_backend=body.get("backend",config.scenario["default_backend"])
        # Rehearsal must never share active physical robots with the report session.
        if body.get("session","report")=="rehearsal":
            from maicon_sim.core.engine import MatchEngine
            runtime=getattr(service.engine,"_runtime",None)
            if runtime is None:
                raise HTTPException(503,"rehearsal configuration requires an active engine writer")
            def configure_rehearsal():
                if service.rehearsal_engine is not None:
                    runtime.remove_engine(service.rehearsal_engine)
                service.rehearsal_generation+=1
                service.rehearsal_engine=MatchEngine(config,session_namespace=f"rehearsal-{service.rehearsal_generation}")
                service.active_session="rehearsal"
                install_backend(service.rehearsal_engine,requested_backend)
                runtime.add_engine(service.rehearsal_engine)
                service.test_mode=body.get("test_mode",service.test_mode)
                return {"match_id":service.rehearsal_engine.match_id,"session":"rehearsal"}
            return await asyncio.wrap_future(runtime.submit_operation(configure_rehearsal))
        result=await service.submit("configure",payload={"config":config})
        service.active_session="report"
        runtime=getattr(service.engine,"_runtime",None)
        if runtime is not None:
            await asyncio.wrap_future(runtime.submit_operation(lambda:install_backend(service.engine,requested_backend)))
        service.test_mode=body.get("test_mode",service.test_mode)
        return result

    @router.post("/fault")
    async def fault(request:Request):
        authorized(request)
        body=await service.body(request,{"fault_id","at_tick","scope","parameters"})
        return await service.submit("fault",payload=body,engine=service.select_engine(request.query_params.get("session")=="rehearsal"))

    @router.post("/shutdown")
    async def shutdown(request:Request):
        authorized(request)
        for engine in (service.engine,service.rehearsal_engine):
            if engine is not None:
                await service.submit("stop",engine=engine)
        service.shutdown_requested=True
        await service.waiters.close()
        return {"accepted":True}
    return router
