import test from "node:test";
import assert from "node:assert/strict";
import {readFile} from "node:fs/promises";

const detail = await readFile(new URL("../components/jobs/JobDetailClient.tsx", import.meta.url), "utf8");
const page = await readFile(new URL("../app/[locale]/jobs/[id]/page.tsx", import.meta.url), "utf8");

test("job detail provides an add to application tracking button", () => {
  assert.match(detail, /onClick=\{addToApplications\}/);
  assert.match(detail, /copy\.addToApplications/);
  assert.match(page, /"addToApplications"/);
});

test("adding a job creates an application with job_id and redirects to its detail", () => {
  assert.match(detail, /apiSend<Application>\("\/api\/v1\/applications","POST",\{job_id:id,status:"saved",source:"job_discovery"\}\)/);
  assert.match(detail, /router\.push\(`\/\$\{locale\}\/applications\/\$\{application\.id\}`\)/);
});
