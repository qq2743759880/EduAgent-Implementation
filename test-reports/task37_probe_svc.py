# -*- coding: utf-8 -*-
import asyncio

async def main():
    from app.database import init_mysql, close_mysql
    await init_mysql()
    try:
        from app.domains.trade.order import service as svc
        from app.common.exceptions import AppException
        # admin user logged in = user_id from auth/me; create directly (series2/cohort4)
        try:
            order = await svc.create_order(100003, series_id=2, cohort_id=4, coupon_id=None)
            print("type:", type(order))
            print("repr:", repr(order))
            print("dump:", order.model_dump(mode="json"))
            print("keys:", list(order.model_dump().keys()))
        except AppException as e:
            print("APPEXC", e.code, e.message)
        except Exception as e:
            import traceback; traceback.print_exc()
    finally:
        await close_mysql()

asyncio.run(main())