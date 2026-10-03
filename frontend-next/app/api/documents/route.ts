import { NextResponse } from "next/server";
import { getBackendHeaders, getBackendUrl } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const backendUrl = getBackendUrl();
    const res = await fetch(`${backendUrl}/documents`, {
      headers: getBackendHeaders(),
      cache: "no-store",
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error.message || "Failed to fetch documents" },
      { status: 502 }
    );
  }
}

export async function DELETE() {
  try {
    const backendUrl = getBackendUrl();
    const res = await fetch(`${backendUrl}/documents/`, {
      method: "DELETE",
      headers: getBackendHeaders(),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error.message || "Failed to clear documents" },
      { status: 502 }
    );
  }
}
