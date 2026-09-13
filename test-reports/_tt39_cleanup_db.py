# -*- coding: utf-8 -*-
"""清理本验收测试残留（仅删/改我创建的测试行，审计可逆）：
1. 给我创建的两笔 pending 订单(80383/80384, order_no 45f5a7/ca6665)置 cancelled，释放其 order_item
2. cohort 7883 current_student_count 从 2 恢复 0
3. 删除 coupon_receive_record id=51005(coupon68,user1)，coupon.receive_count 736 恢复 735
事务化；逐条 print 前置/后置计数。"""
import pymysql
c=pymysql.connect(host="localhost",port=3306,user="root",password="123456",db="edu",charset="utf8mb4",autocommit=False)
cur=c.cursor(pymysql.cursors.DictCursor)
try:
    cur.execute("SELECT id,order_no,order_status FROM `order` WHERE id IN (80383,80384)")
    before=cur.fetchall(); print("订单前置:", before)
    cur.execute("SELECT current_student_count FROM series_cohort WHERE id=7883")
    print("cohort7883 前置:", cur.fetchone())
    cur.execute("SELECT receive_count FROM coupon WHERE id=68")
    print("coupon68 receive_count 前置:", cur.fetchone())
    cur.execute("SELECT COUNT(*) c FROM coupon_receive_record WHERE id=51005")
    print("receive_record51005 前置:", cur.fetchone())

    # 1) 订单置 cancelled + order_item 同步
    for ono in ("6-260904192754-ca6665","6-260904192754-45f5a7"):
        cur.execute("UPDATE `order` SET order_status='cancelled', cancel_at=NOW(), updated_at=NOW() WHERE order_no=%s AND order_status='pending'",(ono,))
        cur.execute("UPDATE order_item SET order_item_status='cancelled', updated_at=NOW() WHERE order_id IN (SELECT id FROM `order` WHERE order_no=%s)",(ono,))
    # 2) 座位恢复 0
    cur.execute("UPDATE series_cohort SET current_student_count=GREATEST(0, current_student_count-2), updated_at=NOW() WHERE id=7883")
    # 3) 删除我创建的领券记录 + 回卷 receive_count
    cur.execute("DELETE FROM coupon_receive_record WHERE id=51005 AND coupon_id=68 AND user_id=1")
    cur.execute("UPDATE coupon SET receive_count=GREATEST(0, receive_count-1) WHERE id=68")
    c.commit()
    print("=== 已提交清理 ===")
    cur.execute("SELECT id,order_no,order_status FROM `order` WHERE id IN (80383,80384)")
    print("订单后置:", cur.fetchall())
    cur.execute("SELECT current_student_count FROM series_cohort WHERE id=7883")
    print("cohort7883 后置:", cur.fetchone())
    cur.execute("SELECT receive_count FROM coupon WHERE id=68")
    print("coupon68 receive_count 后置:", cur.fetchone())
    cur.execute("SELECT COUNT(*) c FROM coupon_receive_record WHERE id=51005")
    print("receive_record51005 后置:", cur.fetchone())
except Exception as e:
    c.rollback(); print("ROLLBACK:", e); raise