import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";
import test from "node:test";

const source = await readFile(new URL("../components/applications/ApplicationsClient.tsx", import.meta.url), "utf8");

test("manual Application creation defaults and submits application_date", () => {
  assert.match(source, /useState\(todayInputValue\)/);
  assert.match(source, /type="date" value=\{applicationDate\}/);
  assert.match(source, /application_date:applicationDate/);
});
