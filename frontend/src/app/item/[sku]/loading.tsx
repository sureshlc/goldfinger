export default function Loading() {
    return (
      <>
    <div className="relative"></div>
        {/* Background Skeleton (optional - shows behind overlay) */}
        <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-white/60 to-transparent"></div>
          {/* Page Header Skeleton */}
        <div>
          <div className="mb-8">
            <div className="h-8 bg-gray-200 rounded w-1/3 mb-4"></div>
            <div className="h-4 bg-gray-200 rounded w-1/4"></div>
          </div>
  
          {/* Main Production Card Skeleton */}
          <div className="border rounded mb-4 bg-white">
            {/* Summary Section */}
            <div className="p-4">
              {/* Status Card */}
              <div className="border-2 rounded-lg p-4 mb-4 bg-gray-50">
                <div className="flex items-center justify-between mb-3">
                  <div className="h-7 bg-gray-200 rounded w-1/4"></div>
                  <div className="text-right">
                    <div className="h-4 bg-gray-200 rounded w-24 mb-2"></div>
                    <div className="h-8 bg-gray-200 rounded w-16"></div>
                  </div>
                </div>
  
                <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
                  <div>
                    <div className="h-3 bg-gray-200 rounded w-20 mb-2"></div>
                    <div className="h-4 bg-gray-200 rounded w-32"></div>
                  </div>
                  <div>
                    <div className="h-3 bg-gray-200 rounded w-16 mb-2"></div>
                    <div className="h-4 bg-gray-200 rounded w-24"></div>
                  </div>
                  <div>
                    <div className="h-3 bg-gray-200 rounded w-28 mb-2"></div>
                    <div className="flex gap-2">
                      <div className="h-8 bg-gray-200 rounded w-20"></div>
                      <div className="h-8 bg-gray-200 rounded w-16"></div>
                    </div>
                  </div>
                </div>
              </div>
  
              {/* Shortage Summary Skeleton */}
              <div className="border border-gray-200 rounded-lg p-3 bg-gray-50 mb-4">
                <div className="h-4 bg-gray-200 rounded w-48 mb-3"></div>
                <div className="space-y-2">
                  <div className="flex justify-between">
                    <div className="h-3 bg-gray-200 rounded w-32"></div>
                    <div className="h-3 bg-gray-200 rounded w-24"></div>
                  </div>
                  <div className="flex justify-between">
                    <div className="h-3 bg-gray-200 rounded w-40"></div>
                    <div className="h-3 bg-gray-200 rounded w-20"></div>
                  </div>
                </div>
              </div>
            </div>
  
            {/* Component Status Section */}
            <div className="border-t">
              <div className="px-4 py-3 bg-gray-100">
                <div className="h-4 bg-gray-200 rounded w-48"></div>
              </div>
              
              <div className="p-4 bg-gray-50">
                <div className="space-y-2">
                  {/* Component Card 1 */}
                  <div className="border-l-4 border-gray-300 bg-white rounded-r p-3 shadow-sm">
                    <div className="h-4 bg-gray-200 rounded w-48 mb-2"></div>
                    <div className="h-3 bg-gray-200 rounded w-32 mb-3"></div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <div>
                        <div className="h-3 bg-gray-200 rounded w-16 mb-1"></div>
                        <div className="h-4 bg-gray-200 rounded w-20"></div>
                      </div>
                      <div>
                        <div className="h-3 bg-gray-200 rounded w-16 mb-1"></div>
                        <div className="h-4 bg-gray-200 rounded w-16"></div>
                      </div>
                    </div>
                  </div>
  
                  {/* Component Card 2 */}
                  <div className="border-l-4 border-gray-300 bg-white rounded-r p-3 shadow-sm">
                    <div className="h-4 bg-gray-200 rounded w-56 mb-2"></div>
                    <div className="h-3 bg-gray-200 rounded w-36 mb-3"></div>
                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                      <div>
                        <div className="h-3 bg-gray-200 rounded w-16 mb-1"></div>
                        <div className="h-4 bg-gray-200 rounded w-20"></div>
                      </div>
                      <div>
                        <div className="h-3 bg-gray-200 rounded w-16 mb-1"></div>
                        <div className="h-4 bg-gray-200 rounded w-16"></div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </>
    );
  }