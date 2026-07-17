from fastapi import APIRouter

from app.api.v1 import auth
from app.api.v1.admin import routes as admin_routes
from app.api.v1.public import routes as public_routes
from app.api.v1.sync import routes as sync_routes

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(auth.router)
api_router.include_router(public_routes.router)
api_router.include_router(admin_routes.router)
api_router.include_router(sync_routes.router)
