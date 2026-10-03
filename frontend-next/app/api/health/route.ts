import { NextResponse } from "next/server";
import { getBackendUrl } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const backendUrl = getBackendUrl();
    const res = await fetch(`${backendUrl}/health`, {
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { status: "error", message: error.message || "Failed to reach backend" },
      { status: 502 }
    );
  }
}
