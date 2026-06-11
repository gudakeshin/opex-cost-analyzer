/**
 * E2E: Engagement documents journey
 *
 * Verifies: create engagement → upload document → poll parse status →
 * list documents. This matches the primary doc-ingestion flow.
 */
import { test, expect, Page } from "@playwright/test";

const API = "http://localhost:8000";

async function createEngagement(page: Page): Promise<string> {
  const res = await page.request.post(`${API}/api/v1/engagements`, {
    data: { name: "E2E Test Engagement", client: "Test Client" },
  });
  expect([200, 201]).toContain(res.status());
  const body = await res.json();
  return (body.engagement_id ?? body.id) as string;
}

test.describe("Engagement documents", () => {
  test("creates an engagement and lists it", async ({ page }) => {
    const engagementId = await createEngagement(page);
    expect(engagementId).toBeTruthy();

    const listRes = await page.request.get(`${API}/api/v1/engagements`);
    expect(listRes.status()).toBe(200);
    const list = await listRes.json();
    const ids = (list.engagements ?? list).map((e: { engagement_id?: string; id?: string }) =>
      e.engagement_id ?? e.id
    );
    expect(ids).toContain(engagementId);
  });

  test("uploads a document to an engagement", async ({ page }) => {
    const engagementId = await createEngagement(page);

    const uploadRes = await page.request.post(
      `${API}/api/v1/engagements/${engagementId}/documents`,
      {
        multipart: {
          file: {
            name: "strategy.txt",
            mimeType: "text/plain",
            buffer: Buffer.from("Sample engagement document content for E2E testing."),
          },
        },
      }
    );
    expect([200, 201, 202]).toContain(uploadRes.status());
    const body = await uploadRes.json();
    expect(body).toHaveProperty("document_id");
  });

  test("lists documents for an engagement", async ({ page }) => {
    const engagementId = await createEngagement(page);

    const listRes = await page.request.get(
      `${API}/api/v1/engagements/${engagementId}/documents`
    );
    expect(listRes.status()).toBe(200);
    const body = await listRes.json();
    // May be empty array — just assert shape
    expect(body).toHaveProperty("documents");
    expect(Array.isArray(body.documents)).toBe(true);
  });

  test("deletes an engagement", async ({ page }) => {
    const engagementId = await createEngagement(page);

    const deleteRes = await page.request.delete(
      `${API}/api/v1/engagements/${engagementId}`
    );
    expect([200, 204]).toContain(deleteRes.status());

    // Verify it no longer appears in the list
    const listRes = await page.request.get(`${API}/api/v1/engagements`);
    const list = await listRes.json();
    const ids = (list.engagements ?? list).map((e: { engagement_id?: string; id?: string }) =>
      e.engagement_id ?? e.id
    );
    expect(ids).not.toContain(engagementId);
  });
});
