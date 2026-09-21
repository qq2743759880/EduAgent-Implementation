import { createServer } from "node:http";
import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const here = path.dirname(fileURLToPath(import.meta.url));
createServer((req, res) => {
  try { res.setHeader("Content-Type", "text/html"); res.end(readFileSync(path.join(here, path.basename(req.url.split("?")[0])))); }
  catch { res.statusCode = 404; res.end("no"); }
}).listen(18899, "127.0.0.1");
