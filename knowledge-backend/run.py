import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )

    from .mdns import start_mdns

@app.on_event("startup")
def startup():
    init_db()
    start_mdns(8000)