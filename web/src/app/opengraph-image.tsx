import { ImageResponse } from "next/og";

export const alt = "Chronicle: every open role, every company";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";
// No params and no data: rendered once at build time and served as a static file, so social
// cards cost no function CPU at request time. Job pages point at this one image.
export const dynamic = "force-static";

export default function Image() {
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
        <div style={{ display: "flex", fontSize: 76, lineHeight: 1.1, letterSpacing: -1.5 }}>
          Every open role. Every company.
        </div>
        <div style={{ display: "flex", fontSize: 24, color: "#525252" }}>
          From each company&apos;s own careers board
        </div>
      </div>
    ),
    size,
  );
}
