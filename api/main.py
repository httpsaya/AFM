from fastapi import FastAPI
from api.routers.counterparty import router

app = FastAPI(title="Counterparty API")
app.include_router(router)
