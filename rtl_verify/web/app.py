from nicegui import ui, app
import structlog
from rtl_verify.database import init_db, close_db

log = structlog.get_logger()

def main():
    # Initialize database on startup
    app.on_startup(init_db)
    app.on_shutdown(close_db)
    
    # Register pages
    from rtl_verify.web.pages import dashboard, iteration, rtl_viewer, verification, coverage, comparison, settings
    
    ui.run(title='RTL Verify', port=8080, reload=False, dark=True)

if __name__ in {"__main__", "__mp_main__"}:
    main()
