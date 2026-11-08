import asyncio
import copy
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import Response
from .errors import invalid, public_error


def sim_router(service):
    router=APIRouter()
    def slot_for(request,code=None):
        slot=service.authenticate(code if code is not None else request.query_params.get("mission_code"))
        service.check_session(request,service.active_engine)
        # No cross-slot selector is part of this bridge.
        requested=request.query_params.get("slot")
        if requested is not None and requested!=slot:
            raise HTTPException(403,"robot belongs to another team")
        return slot

    @router.get("/sim/session")
    async def session(request:Request):
        slot=slot_for(request)
        engine=service.active_engine
        return {"match_id":engine.match_id,"episode_index":getattr(engine,"episode_index",1),
                "slot":slot,"camp":"BLUE" if slot.startswith("B") else "RED",
                "capabilities":copy.deepcopy(getattr(service.gateway,"capabilities",{
                    "rgb":False,"semantic":True,"lidar":True,"depth":False})),"schema_version":"1.0"}

    @router.get("/sim/map-prior")
    async def map_prior(request:Request):
        slot_for(request)
        return service.public_map()

    @router.get("/sim/calibration")
    async def calibration(request:Request):
        slot_for(request)
        return service.calibration()

    def sensor_handler(channel):
        async def handler(request:Request):
            slot=slot_for(request)
            data=await asyncio.to_thread(service.sensor,slot,channel)
            if channel=="camera":
                blob,headers=data
                return Response(blob,media_type="image/jpeg",headers=headers)
            return data
        return handler
    for channel in ("state","match","odom","imu","scan","semantic","camera"):
        router.add_api_route("/sim/robot/v1/"+channel,sensor_handler(channel),methods=["GET"])

    def command_handler(kind):
        async def handler(request:Request):
            body=await service.body(request)
            slot=slot_for(request,body.get("mission_code"))
            payload=service.validate_robot(kind,body)
            return await service.submit(kind,slot,payload,engine=service.active_engine,path=request.url.path,request=request)
        return handler
    for kind in ("cmd_vel","gimbal","fire","oled"):
        router.add_api_route("/sim/robot/v1/"+kind,command_handler(kind),methods=["POST"])

    @router.get("/api/report/drone")
    async def drone(request:Request):
        slot=slot_for(request)
        camera=request.query_params.get("camera")
        if camera is not None and camera not in ("main","test1","test2"):
            invalid("camera","unknown camera")
        if service.gateway is None:
            raise HTTPException(503,"camera has not produced a frame")
        try:
            blob,headers=await asyncio.to_thread(service.gateway.get_drone,slot,camera=camera,test_mode=service.test_mode)
        except Exception as error:
            raise public_error(error) from None
        return Response(blob,media_type="image/jpeg",headers=headers)
    return router
