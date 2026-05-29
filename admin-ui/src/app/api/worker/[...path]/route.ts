import { NextRequest, NextResponse } from "next/server";

const DEFAULT_WORKER_URL = "http://161.118.208.146:8080";

type RouteContext = {
  params: Promise<{ path?: string[] }>;
};

async function forward(request: NextRequest, context: RouteContext) {
  const { path = [] } = await context.params;
  const baseUrl = process.env.WORKER_API_URL || DEFAULT_WORKER_URL;
  const upstream = new URL(path.join("/"), baseUrl.endsWith("/") ? baseUrl : `${baseUrl}/`);
  upstream.search = request.nextUrl.search;

  const headers = new Headers(request.headers);
  headers.delete("host");
  headers.delete("connection");

  const hasBody = !["GET", "HEAD"].includes(request.method);
  const response = await fetch(upstream, {
    method: request.method,
    headers,
    body: hasBody ? await request.text() : undefined,
    cache: "no-store",
  });

  const body = await response.arrayBuffer();
  const responseHeaders = new Headers(response.headers);
  responseHeaders.delete("content-encoding");
  responseHeaders.delete("content-length");

  return new NextResponse(body, {
    status: response.status,
    statusText: response.statusText,
    headers: responseHeaders,
  });
}

export async function GET(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}

export async function POST(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}

export async function PATCH(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}

export async function DELETE(request: NextRequest, context: RouteContext) {
  return forward(request, context);
}
