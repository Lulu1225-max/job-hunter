import assert from "node:assert/strict";
import {readFileSync} from "node:fs";
import test from "node:test";

const card = readFileSync(new URL("../components/applications/ApplicationCard.tsx", import.meta.url), "utf8");
const client = readFileSync(new URL("../components/applications/ApplicationsClient.tsx", import.meta.url), "utf8");
const zh = JSON.parse(readFileSync(new URL("../messages/zh.json", import.meta.url), "utf8"));

const expected = {
  saved: "收藏",
  applied: "已投递",
  oa: "笔试/测评",
  interview: "面试",
  final_interview: "终面",
  offer: "Offer",
  rejected: "被拒",
  withdrawn: "已撤回",
};

test("every canonical Application status has the correct Chinese label", () => {
  assert.deepEqual(Object.fromEntries(Object.keys(expected).map((status) => [status, zh.status[status]])), expected);
});

test("Final Interview sends and renders the same canonical status", () => {
  assert.match(card, /value=\{status\}>\{t\(`status\.\$\{status\}`\)\}/);
  assert.match(card, /"final_interview"/);
  assert.match(client, /encodeURIComponent\(status\)/);
  assert.equal(zh.status.final_interview, "终面");
  assert.notEqual(zh.status.final_interview, zh.status.saved);
});
