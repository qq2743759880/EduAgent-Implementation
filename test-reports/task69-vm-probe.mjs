/* 探测 VM 192.168.85.101 中间件端口连通性 + Milvus healthz */
import net from "node:net";

const HOST = "192.168.85.101";
const targets = [
  ["Redis", 6379],
  ["Milvus", 19530],
  ["MongoDB", 27017],
  ["MinIO", 9000],
  ["Neo4j", 7687],
  ["Milvus healthz", 9091],
];

function tcp(host, port, timeout = 4000) {
  return new Promise((resolve) => {
    const sock = new net.Socket();
    sock.setTimeout(timeout);
    sock.once("connect", () => { sock.destroy(); resolve("可达"); });
    sock.once("timeout", () => { sock.destroy(); resolve("超时"); });
    sock.once("error", (e) => { sock.destroy(); resolve(`错误(${e.code})`); });
    sock.connect(port, host);
  });
}

for (const [name, port] of targets) process.stdout.write(`${name.padEnd(16)}(:${port}) -> `);
console.log();

for (const [name, port] of targets) {
  const r = await tcp(HOST, port);
  console.log(`${name.padEnd(18)} :${port}  ${r}`);
}

try {
  const hz = await fetch(`http://${HOST}:9091/healthz`).then((r) => r.text());
  console.log("\nMilvus /healthz:", hz.slice(0, 80));
} catch (e) {
  console.log("\nMilvus /healthz 不可达:", e.message);
}
try {
  const ping = await fetch(`http://${HOST}:9000/minio/health/live`).then((r) => `HTTP ${r.status}`);
  console.log("MinIO /minio/health/live:", ping);
} catch (e) {
  console.log("MinIO health 不可达:", e.message);
}