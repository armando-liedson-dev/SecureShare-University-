"""Application composition; features live in separate routers and services."""
import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.auth import router as auth_router
from app.admin import router as admin_router, reconcile_documents
from app.documents import router as documents_router
from app.db import init_db, get_connection
from app.storage_client import open_node_client, close_node_client

logger=logging.getLogger('secureshare')


async def scheduled_repair(stop:asyncio.Event,interval:int):
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(),timeout=interval)
        except asyncio.TimeoutError:
            try:
                await reconcile_documents(30)
            except Exception:
                logger.exception('Erro na reconciliação de réplicas')


@asynccontextmanager
async def lifespan(application):
    init_db()
    await open_node_client()
    stop=asyncio.Event()
    interval=int(os.getenv('RECONCILE_INTERVAL_SECONDS','90'))
    task=asyncio.create_task(scheduled_repair(stop,interval)) if interval>0 else None
    yield
    stop.set()
    if task:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
    await close_node_client()


app=FastAPI(title='SecureShare Universitário',version='1.0.0',
            description='Partilha segura, autorização departamental e replicação em dois nós',
            lifespan=lifespan)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(admin_router)

origins=[o.strip() for o in os.getenv('CORS_ORIGINS','').split(',') if o.strip()]
if origins:
    app.add_middleware(CORSMiddleware,allow_origins=origins,
                       allow_credentials=False,allow_methods=['GET','POST','DELETE','PATCH'],allow_headers=['Authorization','Content-Type'])

@app.middleware('http')
async def security_headers(request,call_next):
    resp=await call_next(request)
    resp.headers['X-Content-Type-Options']='nosniff'
    resp.headers['X-Frame-Options']='DENY'
    resp.headers['Referrer-Policy']='no-referrer'
    resp.headers['Cache-Control']='no-store'
    resp.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'"
    if request.url.scheme=='https':
        resp.headers['Strict-Transport-Security']='max-age=3600'
    return resp

@app.get('/health')
def health():
    try:
        with get_connection() as conn:
            conn.execute('SELECT 1')
    except Exception:
        return JSONResponse(status_code=503,content={'status':'degraded','database':'unavailable'})
    return {'status':'ok','database':'connected'}

ROOT=Path(__file__).resolve().parent.parent
FRONTEND=ROOT/'web'
if FRONTEND.is_dir():
    app.mount('/assets',StaticFiles(directory=FRONTEND),name='web-assets')

    @app.get('/',include_in_schema=False)
    def homepage():
        return FileResponse(FRONTEND/'index.html')
