// Reads {price, outcome, cluster} JSON on stdin; prints the explorer's statistics as JSON.
import { brier, fitRecalibration, reliabilityBins } from "../../docs/stats.js";

const chunks = [];
for await (const chunk of process.stdin) chunks.push(chunk);
const { price, outcome, cluster } = JSON.parse(Buffer.concat(chunks).toString());
console.log(JSON.stringify({
  brier: brier(price, outcome),
  fit: fitRecalibration(price, outcome, cluster),
  bins: reliabilityBins(price, outcome, 10),
}));
