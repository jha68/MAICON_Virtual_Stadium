"""Public and supervisor applications are separate trust surfaces."""
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from .service import ServerService
from .report_routes import report_router
from .rehearsal_routes import rehearsal_router
from .sim_robot_routes import sim_router
from .admin_routes import admin_router
from .metrics import HTTPMetricsMiddleware


def create_apps(engine,gateway=None,admin_token=None,rehearsal_engine=None):
    service=ServerService(engine,gateway,admin_token,rehearsal_engine)
    public=FastAPI(title="MAICON simulation participant API",docs_url=None,redoc_url=None)
    admin=FastAPI(title="MAICON simulation supervisor API",docs_url=None,redoc_url=None)
    public.state.service=admin.state.service=service
    public.add_middleware(HTTPMetricsMiddleware,metrics=service.http_stats)
    admin.add_middleware(HTTPMetricsMiddleware,metrics=service.http_stats)
    public.include_router(report_router(service))
    public.include_router(rehearsal_router(service))
    public.include_router(sim_router(service))
    admin.include_router(admin_router(service))
    async def sanitized_validation(request,error):
        return JSONResponse(status_code=422,content={"detail":[{
            "loc":list(e["loc"]),"msg":e["msg"],"type":e["type"]} for e in error.errors()]})
    public.add_exception_handler(RequestValidationError,sanitized_validation)
    admin.add_exception_handler(RequestValidationError,sanitized_validation)
    return public,admin
