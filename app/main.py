from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.db.session import engine, Base, SessionLocal
from app.routes.auth import router as auth_router
from app.routes.plans import router as plans_router
from app.routes.purchases import router as purchases_router
from app.models.models import SubscriptionPlan
from app.core import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("demo_saas_app")

# Automatically generate tables for SQLite/PostgreSQL databases on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="WhiteNet Payment Test Client SaaS API",
    description="Demo third-party application integrated with WhiteNet Payment provider APIs.",
    version="1.0.0"
)

# Enable CORS for frontend integrations
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,  # Loaded from env (CORS_ORIGINS)
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register endpoints
app.include_router(auth_router)
app.include_router(plans_router)
app.include_router(purchases_router)

@app.on_event("startup")
def startup_event():
    # Automatically populate core SaaS subscription plans on first startup
    db = SessionLocal()
    try:
        plan_count = db.query(SubscriptionPlan).count()
        if plan_count == 0:
            logger.info("Plans table is empty. Auto-seeding default plans...")
            seeds = [
                SubscriptionPlan(
                    id=1,
                    name="Starter",
                    description="Perfect for individuals testing out the SaaS ecosystem.",
                    price=100.0,
                    features=["Basic analytics", "Up to 5 integrations", "Email support", "Single user license"]
                ),
                SubscriptionPlan(
                    id=2,
                    name="Professional",
                    description="Our most popular plan. Designed for small teams and developers.",
                    price=500.0,
                    features=["Advanced analytics", "Unlimited integrations", "24/7 Priority support", "Up to 5 user licenses", "API Access"]
                ),
                SubscriptionPlan(
                    id=3,
                    name="Enterprise",
                    description="Fully customizable solution built for large corporate scale.",
                    price=1000.0,
                    features=["Custom reports", "Dedicated Account Manager", "SLA uptime agreement", "Unlimited users", "Whitelabel branding"]
                )
            ]
            for plan in seeds:
                db.add(plan)
            db.commit()
            logger.info("Default subscription plans seeded successfully.")
    except Exception as e:
        logger.error(f"Error seeding database: {str(e)}")
    finally:
        db.close()

@app.get("/")
def read_root():
    return {
        "app": "WhiteNet Payment Integration Demo SaaS API",
        "status": "online",
        "version": "1.0.0"
    }
