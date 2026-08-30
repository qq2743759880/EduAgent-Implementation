# task34 清除前快照

- 生成时间：2026-08-30T13:12:38
- Milvus：http://192.168.85.101:19530

## edu_knowledge
- rows=4983 loaded=Loaded
- partitions: {"_default": 4976, "user_970": 2, "user_996": 2, "user_1000": 2, "course_public": 0, "user_100013": 1}
- indexes: {"dense_vec": {"type": "IVF_FLAT", "metric": "COSINE", "params": null}, "sparse_vec": {"type": "SPARSE_INVERTED_INDEX", "metric": "IP", "params": null}}
- schema_fields(9): id(5), chunk_id(21), content(21), content_type(21), source_file(21), dense_vec(101), sparse_vec(104), tenant_id(21), visibility(21)
- raw_dup_stats: {"raw_content_non_empty": 4982, "contextualized": 0, "meaning": "raw_content 非空 = 每 chunk 存双份（前缀版 content + 原文 raw_content）"}
## user_memory
- rows=9 loaded=Loaded
- partitions: {"_default": 9}
- indexes: {"vector": {"type": "AUTOINDEX", "metric": "COSINE", "params": null}}
## pf_bagu_kb
- rows=5724 loaded=Loaded
- partitions: {"_default": 5724}
- indexes: {"dense": {"type": "AUTOINDEX", "metric": "COSINE", "params": null}}
## neo4j
- {"nodes": 1330, "rels": 6194}

> 依据：GWT⑤ 清除前快照（schema 定义 + 计数）先落盘，作为回滚依据。