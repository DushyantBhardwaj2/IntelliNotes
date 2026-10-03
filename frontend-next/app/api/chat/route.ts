import { NextRequest, NextResponse } from "next/server";
import { getBackendHeaders, getBackendUrl } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const backendUrl = getBackendUrl();
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
      ...getBackendHeaders(),
    };

    // Forward client IP if present
    const forwardedFor = req.headers.get("x-forwarded-for");
    if (forwardedFor) {
      headers["X-Forwarded-For"] = forwardedFor;
    }

    const res = await fetch(`${backendUrl}/chat/`, {
      method: "POST",
      headers,
      body: JSON.stringify(body),
    });

    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error.message || "Failed to communicate with chat backend" },
      { status: 502 }
    );
  }
}
