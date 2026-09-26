import { ImageResponse } from "next/og";
import { getJob } from "@/lib/api";
import { formatPay } from "@/lib/format";
import { formatLocation } from "@/lib/utils";

export const alt = "Job on Chronicle";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
export const revalidate = 3600;

// The social card for a job: title, company, and only the facts the posting states.
export default async function Image({ params }: { params: { id: string } | Promise<{ id: string }> }) {
  const { id } = await params;
  const job = await getJob(Number(id)).catch(() => null);
  const title = job?.title ?? "Every open role. Every company.";
  const facts = job
    ? [job.company_name, formatLocation(job.location_normalized) || null, job.remote ? "Remote" : null, formatPay(job)]
        .filter(Boolean)
        .join("  ·  ")
    : "";
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#ffffff",
          color: "#000000",
          padding: "72px 80px",
          borderBottom: "16px solid #000000",
        }}
      >
        <div style={{ display: "flex", fontSize: 34, letterSpacing: -0.5 }}>Chronicle</div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div style={{ display: "flex", fontSize: title.length > 60 ? 60 : 76, lineHeight: 1.1, letterSpacing: -1.5 }}>
            {title.length > 110 ? `${title.slice(0, 109)}…` : title}
          </div>
          {facts && <div style={{ display: "flex", marginTop: 32, fontSize: 30, color: "#525252" }}>{facts}</div>}
        </div>
        <div style={{ display: "flex", fontSize: 24, color: "#525252" }}>
          {job?.is_active === false ? "This role is closed" : "From the company's own careers board"}
        </div>
      </div>
    ),
    size,
  );
}
