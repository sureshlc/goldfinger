import Link from "next/link";

export default function NotFound() {
  return (
    <div className="min-h-[calc(100vh-5rem)] bg-gradient-to-b from-blue-50 to-white flex flex-col items-center justify-center px-4">
      <div className="bg-white rounded-xl shadow border border-gray-200 p-10 text-center max-w-md">
        <div className="text-6xl font-bold text-blue-600 mb-2">404</div>
        <h1 className="text-xl font-bold text-gray-900 mb-2">Page Not Found</h1>
        <p className="text-gray-500 text-sm mb-6">
          The page you&apos;re looking for doesn&apos;t exist or has been moved.
        </p>
        <Link
          href="/"
          className="inline-flex items-center gap-1.5 bg-blue-600 text-white px-5 py-2.5 rounded-lg text-sm font-medium hover:bg-blue-700 transition"
        >
          Back to Home
        </Link>
      </div>
    </div>
  );
}
