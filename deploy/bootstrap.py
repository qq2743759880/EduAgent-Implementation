"""Install the current schema and first administrator into an EMPTY database.

No business data dumps, password defaults, table drops or implicit migrations.
An installation marker permits repeat starts without modifying existing users.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path


def require_empty_database(tables):
    if tables:
        raise ValueError('Installation requires an empty database; existing tables will not be modified')


def validate_admin_password(password):
    if len(password.encode('utf-8')) < 12 or len(password.encode('utf-8')) > 72 or password.startswith(('REPLACE_', 'GENERATE_')):
        raise ValueError('Use a private administrator password of 12–72 UTF-8 bytes')


def install(values: dict, folder: Path) -> dict:
    import bcrypt
    import pymysql
    from pymysql.constants import CLIENT

    password = values.get('ADMIN_PASSWORD', '')
    validate_admin_password(password)
    sql = (folder / 'schema.sql').read_bytes()
    schema_sha = hashlib.sha256(sql).hexdigest()
    metadata = json.loads((folder / 'schema-manifest.json').read_text(encoding='utf-8'))
    if schema_sha != metadata['sha256']:
        raise ValueError('Schema snapshot does not match its manifest')
    conn = pymysql.connect(host=values.get('MYSQL_HOST', 'mysql'), port=int(values.get('MYSQL_PORT', '3306')),
                           user=values['MYSQL_USER'], password=values['MYSQL_PASSWORD'],
                           database=values['MYSQL_DATABASE'], charset='utf8mb4',
                           client_flag=CLIENT.MULTI_STATEMENTS)
    try:
        with conn.cursor() as cur:
            cur.execute('SHOW TABLES')
            tables = [str(row[0]) for row in cur.fetchall()]
            if 'edu_installation' in tables:
                cur.execute('SELECT schema_sha256 FROM edu_installation WHERE id=1')
                marker = cur.fetchone()
                if not marker or marker[0] != schema_sha:
                    raise ValueError('Existing installation needs an explicit schema upgrade; refusing changes')
                cur.execute('SELECT a.password_hash,a.role_code FROM sys_user u JOIN sys_user_auth a ON a.user_id=u.id '
                            'WHERE u.account=%s AND u.yn=1 AND a.yn=1', (values.get('ADMIN_ACCOUNT', 'admin'),))
                account = cur.fetchone()
                if not account or account[1] != 'admin' or not bcrypt.checkpw(password.encode(), account[0].encode()):
                    raise ValueError('Private administrator configuration differs from the installed database; restore its original config')
                return {'status': 'already-installed', 'tables': len(tables), 'schema_sha256': schema_sha}
            require_empty_database(tables)
            cur.execute(sql.decode('utf-8'))
            while cur.nextset():
                pass
            cur.execute("INSERT INTO sys_user(account,username,nickname,created_at,updated_at) VALUES(%s,%s,%s,NOW(),NOW())",
                        (values.get('ADMIN_ACCOUNT', 'admin'), 'Administrator', 'Administrator'))
            admin_id = cur.lastrowid
            hashed = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt(rounds=12)).decode()
            cur.execute("INSERT INTO sys_user_auth(user_id,password_hash,role_code,created_at,updated_at) VALUES(%s,%s,'admin',NOW(),NOW())",
                        (admin_id, hashed))
            cur.execute("INSERT INTO org_institution(id,institution_code,institution_name,institution_type,created_at,updated_at) "
                        "VALUES(1,'LOCAL','Local Learning','training_center',NOW(),NOW())")
            for id_, code, name, objective, marking in ((1,'single_choice','单选题',1,1),(2,'multiple_choice','多选题',1,1),
                                                       (3,'true_false','判断题',1,1),(4,'fill_blank','填空题',1,0),(5,'short_answer','简答题',0,0)):
                cur.execute('INSERT INTO dim_question_type(id,type_code,type_name,objective_flag,auto_marking_flag,sort_no,created_at,updated_at) '
                            'VALUES(%s,%s,%s,%s,%s,%s,NOW(),NOW())', (id_, code, name, objective, marking, id_))
            cur.execute('CREATE TABLE alembic_version(version_num VARCHAR(32) NOT NULL PRIMARY KEY)')
            for head in metadata['alembic_heads']:
                cur.execute('INSERT INTO alembic_version(version_num) VALUES(%s)', (head,))
            cur.execute('CREATE TABLE edu_installation(id TINYINT NOT NULL PRIMARY KEY,schema_sha256 CHAR(64) NOT NULL,created_at DATETIME NOT NULL)')
            cur.execute('INSERT INTO edu_installation(id,schema_sha256,created_at) VALUES(1,%s,NOW())', (schema_sha,))
            conn.commit()
            cur.execute('SHOW TABLES')
            count = len(cur.fetchall())
        return {'status': 'installed', 'tables': count, 'admin_account': values.get('ADMIN_ACCOUNT', 'admin'),
                'schema_sha256': schema_sha, 'alembic_heads': metadata['alembic_heads']}
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path)
    parser.add_argument('--initialize-rag', action='store_true')
    args = parser.parse_args()
    values = dict(os.environ)
    if args.env_file:
        from portable import read_env
        values.update(read_env(args.env_file))
    print(json.dumps(install(values, Path(__file__).resolve().parent), ensure_ascii=False))
    if args.initialize_rag:
        # Reuse the existing collection contract; never replace or clear one.
        from app.database import init_milvus, get_milvus_client, close_milvus
        from app.knowledge.importer.loader import ensure_collection_exists, COLLECTION_NAME
        init_milvus()
        try:
            created = ensure_collection_exists()
            get_milvus_client().load_collection(COLLECTION_NAME)
            print(json.dumps({'rag_collection': COLLECTION_NAME, 'created': created, 'loaded': True}))
        finally:
            close_milvus()


if __name__ == '__main__':
    main()
