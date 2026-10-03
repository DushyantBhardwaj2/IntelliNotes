import { NextRequest, NextResponse } from "next/server";
import { getBackendHeaders, getBackendUrl } from "@/lib/backend";

export const dynamic = "force-dynamic";

export async function DELETE(
  req: NextRequest,
  { params }: { params: { docId: string } }
) {
  try {
    const { docId } = params;
    const backendUrl = getBackendUrl();
    const res = await fetch(`${backendUrl}/documents/${encodeURIComponent(docId)}`, {
      method: "DELETE",
      headers: getBackendHeaders(),
    });
    const data = await res.json();
    return NextResponse.json(data, { status: res.status });
  } catch (error: any) {
    return NextResponse.json(
      { detail: error.message || "Failed to delete document" },
      { status: 502 }
    );
  }
}
