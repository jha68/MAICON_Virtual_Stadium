from .report_routes import report_router


def rehearsal_router(service):
    return report_router(service,"/api/rehearsal",rehearsal=True)
