from fastapi import APIRouter, Request


def report_router(service,prefix="/api/report",rehearsal=False):
    router=APIRouter(prefix=prefix)
    def get_handler(kind):
        async def handler(request:Request):
            return await service.report_get(kind,request,rehearsal)
        return handler
    def post_handler(kind):
        async def handler(request:Request):
            return await service.report_post(kind,request,rehearsal)
        return handler
    for kind in ("me","order","target"):
        router.add_api_route("/"+kind,get_handler(kind),methods=["GET"])
    for route,kind in (("ready","ready"),("interpretation","m1"),("detection","m3"),("situation","m6")):
        router.add_api_route("/"+route,post_handler(kind),methods=["POST"])
    return router
