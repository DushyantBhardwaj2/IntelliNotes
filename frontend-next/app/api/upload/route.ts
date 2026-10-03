import { NextRequest, NextResponse } from "next/server";
import { getBackendHeaders, getBackendUrl } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const formData = await req.formData();
    const backendUrl = getBackendUrl();
    const headers: Record<string, string> = { ...getBackendHeaders() };

    const forwardedFor = req.headers.get("x-forwarded-for");
    if (forwardedFor) {
      headers["X-Forwarded-For"] = forwardedFor;
    }

    const res = await fetch(`${backendUrl}/upload-document/`, {
      method: "POST",
      headers,
      body: formData,
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error.message || "Failed to upload document" },
      { status: 502 }
    );
  }
}
