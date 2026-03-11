"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";

export interface BOMComponent {
  item_id: string;
  item_name: string;
  item_sku: string;
  quantity_required: number;
  unit: string;
  level?: number;
}

export interface ComponentAvailability {
  item_id: string;
  item_name: string;
  item_sku: string;
  available_quantity: number;
  required_quantity?: number;
  required_for_desired_qty?: number;
  sufficient?: boolean;
  display_quantity?: string;
  max_units_possible?: number;
  unit?: string;
}

export interface Shortage {
  item_id: string;
  item_name: string;
  item_sku: string;
  shortage_quantity: number;
  required_quantity?: number;
  available_quantity?: number;
  unit?: string;
  reason?: string;
}

export interface ProductionAnalysisResponse {
  item_id: string;
  item_name: string;
  item_sku: string;
  can_produce: boolean;
  max_quantity_producible: number;
  limiting_component?: string;
  bom_components: BOMComponent[];
  component_availability: ComponentAvailability[];
  shortages: Shortage[];
  location_name?: string;
}

interface ProductionSectionProps {
  productionData: ProductionAnalysisResponse;
  currentQuantity: number;
  sku: string;
  isExpanded?: boolean;
}

const INDENT_PER_LEVEL = 24;

const ProductionSection: React.FC<ProductionSectionProps> = ({
  productionData,
  currentQuantity,
  sku,
  isExpanded = false,
}) => {
  const router = useRouter();
  const [quantity, setQuantity] = useState(currentQuantity.toString());
  const [isUpdating, setIsUpdating] = useState(false);
  const [showAllComponents, setShowAllComponents] = useState(isExpanded);
  const [showAllShortages, setShowAllShortages] = useState(isExpanded);

  // Helper function to format numbers intelligently
  const formatQuantity = (value: number): string => {
    if (Number.isInteger(value)) {
      return value.toString();
    }
    return parseFloat(value.toFixed(5)).toString();
  };

  // Helper function for available quantity (max 2 decimals)
  const formatAvailable = (value: number): string => {
    if (Number.isInteger(value)) {
      return value.toString();
    }
    return parseFloat(value.toFixed(2)).toString();
  };

  useEffect(() => {
    setIsUpdating(false);
  }, [currentQuantity]);

  useEffect(() => {
    setShowAllComponents(isExpanded);
    setShowAllShortages(isExpanded);
  }, [isExpanded]);

  useEffect(() => {
    setQuantity(currentQuantity.toString());
  }, [currentQuantity]);

  const handleQuantityUpdate = () => {
    const newQty = parseInt(quantity) || 1;
    if (newQty !== currentQuantity && newQty > 0) {
      setIsUpdating(true);
      router.push(`/item/${sku}?quantity=${newQty}`);
    }
  };

  // Merge BOM and availability data
  const mergedComponents = productionData.bom_components.map((bomComp) => {
    const availability = productionData.component_availability.find(
      (avail) => avail.item_sku === bomComp.item_sku
    );
    const shortage = productionData.shortages.find(
      (s) => s.item_sku === bomComp.item_sku
    );

    const hasShortage = !!shortage;
    const availableQty = availability?.available_quantity || 0;
    const sufficient = !hasShortage && availableQty >= bomComp.quantity_required;

    return {
      ...bomComp,
      available_quantity: availableQty,
      required_for_desired_qty: availability?.required_for_desired_qty,
      max_units_possible: availability?.max_units_possible || 0,
      display_quantity: availability?.display_quantity,
      has_shortage: hasShortage,
      shortage_info: shortage,
      sufficient: sufficient,
    };
  });

  // Show 2 components initially
  const hasMany = mergedComponents.length > 2;
  const displayedComponents = showAllComponents
    ? mergedComponents
    : mergedComponents.slice(0, 2);

  // Calculate progress percentage for a component
  const getProgressPercent = (comp: typeof mergedComponents[0]): number => {
    const required = comp.required_for_desired_qty ?? comp.quantity_required * currentQuantity;
    if (required <= 0) return 100;
    return Math.min(100, (comp.available_quantity / required) * 100);
  };

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden mb-6">
      {/* Always Visible Summary Section */}
      <div className="p-6">
        {/* Main Status Card */}
        <div className={`border rounded-xl p-4 mb-4 ${productionData.can_produce ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'}`}>
          <div className="flex items-center justify-between mb-3">
            <h3 className={`text-xl font-bold ${productionData.can_produce ? 'text-green-700' : 'text-red-700'}`}>
              {productionData.can_produce ? "Can Produce" : "Cannot Produce"}
            </h3>
            <div className="text-right">
              <p className="text-sm text-gray-600">Max Producible</p>
              <p className="font-bold text-2xl text-blue-600">{productionData.max_quantity_producible}</p>
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 mb-3">
            <div>
              <p className="text-xs text-gray-600">Item Name</p>
              <p className="font-semibold text-sm">{productionData.item_name}</p>
            </div>
            <div>
              <p className="text-xs text-gray-600">SKU</p>
              <p className="font-semibold text-sm">{productionData.item_sku}</p>
            </div>
            <div>
              <p className="text-xs text-gray-600">Desired Quantity</p>
              <div className="flex gap-2">
                <input
                  type="number"
                  min="1"
                  value={quantity}
                  onChange={(e) => setQuantity(e.target.value)}
                  disabled={isUpdating}
                  className="border rounded px-2 py-1 w-20 min-w-[80px] max-w-[120px] text-sm disabled:bg-gray-100"
                />
                <button
                  onClick={handleQuantityUpdate}
                  disabled={isUpdating || parseInt(quantity) === currentQuantity}
                  className={`px-3 py-1 text-white rounded text-xs font-semibold transition flex items-center gap-1 ${
                    isUpdating || parseInt(quantity) === currentQuantity
                      ? 'bg-gray-400 cursor-not-allowed'
                      : 'bg-blue-600 hover:bg-blue-700'
                  }`}
                >
                  {isUpdating ? (
                    <>
                      <svg className="animate-spin h-3 w-3" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Updating...
                    </>
                  ) : (
                    'Update'
                  )}
                </button>
              </div>
            </div>
          </div>

          {productionData.limiting_component && (
            <div className="p-2 bg-yellow-100 border border-yellow-400 rounded">
              <p className="font-semibold text-yellow-800 text-sm">
                Limiting: {productionData.limiting_component}
              </p>
            </div>
          )}
        </div>

        {/* Quick Shortage Summary */}
        {productionData.shortages.length > 0 && (
          <div className="border border-red-200 rounded-xl p-4 bg-red-50">
            <h4 className="font-bold text-red-700 mb-3 text-sm">
              Critical Shortages ({productionData.shortages.length} components)
            </h4>
            <div className="space-y-2">
              {(showAllShortages ? productionData.shortages : productionData.shortages.slice(0, 3)).map((shortage, idx) => (
                <div key={idx} className="flex justify-between items-center text-sm bg-white rounded-lg px-3 py-2 border border-red-100">
                  <span className="font-medium text-gray-900">{shortage.item_name}</span>
                  <span className="text-red-600 font-semibold text-xs">Short: {formatQuantity(shortage.shortage_quantity)} {shortage.unit}</span>
                </div>
              ))}
              {productionData.shortages.length > 3 && (
                <button
                  onClick={() => setShowAllShortages(!showAllShortages)}
                  className="text-xs text-blue-600 hover:text-blue-800 font-medium mt-1 underline"
                >
                  {showAllShortages
                    ? 'Show less'
                    : `Show ${productionData.shortages.length - 3} more...`
                  }
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Component Status Section */}
      <div className="border-t border-gray-200">
        <div className="px-6 py-4 bg-gray-50 flex justify-between items-center">
          <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
            Component Status ({mergedComponents.length} components)
          </h2>
          <span className="text-xs text-gray-500">BOM hierarchy with availability</span>
        </div>

        <div className="p-6 relative">
          {/* Component list */}
          <div className={`space-y-3 ${hasMany && !showAllComponents ? 'relative pb-8' : ''}`}>
            {displayedComponents.map((comp, idx) => {
              const borderColor = comp.has_shortage
                ? 'border-red-400'
                : comp.sufficient
                ? 'border-green-400'
                : 'border-yellow-400';

              const bgColor = comp.has_shortage
                ? 'bg-red-50'
                : comp.sufficient
                ? 'bg-white'
                : 'bg-yellow-50';

              const isPartialSecond = hasMany && !showAllComponents && idx === 1;
              const progressPercent = getProgressPercent(comp);

              return (
                <div
                  key={idx}
                  style={{ marginLeft: (comp.level ?? 0) * INDENT_PER_LEVEL }}
                  className={`border-l-4 ${borderColor} ${bgColor} rounded-r-lg p-4 shadow-sm border border-gray-100 ${isPartialSecond ? 'relative' : ''}`}
                >
                  {isPartialSecond && (
                    <div className="absolute inset-0 bg-gradient-to-b from-transparent to-white pointer-events-none z-10 rounded-r-lg"></div>
                  )}

                  <div className={`${isPartialSecond ? 'relative z-0' : ''}`}>
                    <div className="flex justify-between items-start">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <p className="font-semibold text-sm">{comp.item_name}</p>
                          {comp.level !== undefined && comp.level > 0 && (
                            <span className="text-xs bg-gray-200 px-2 py-0.5 rounded">L{comp.level}</span>
                          )}
                        </div>
                        <p className="text-xs text-gray-500 mb-2">SKU: {comp.item_sku}</p>
                      </div>
                      <p className={`text-xs font-bold px-2 py-1 rounded ${comp.sufficient ? 'text-green-700 bg-green-100' : 'text-red-700 bg-red-100'}`}>
                        {comp.sufficient ? 'OK' : 'SHORT'}
                      </p>
                    </div>

                    <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                      <div>
                        <p className="text-gray-500">Required</p>
                        <p className="font-semibold">{formatQuantity(comp.quantity_required)} {comp.unit}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Available</p>
                        <p className="font-semibold">{comp.display_quantity || formatAvailable(comp.available_quantity)}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Max Units</p>
                        <p className="font-semibold">{comp.display_quantity || comp.max_units_possible}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Status</p>
                        <p className={`font-semibold ${comp.sufficient ? 'text-green-600' : 'text-red-600'}`}>
                          {comp.sufficient ? 'OK' : 'Short'}
                        </p>
                      </div>
                    </div>

                    {/* Progress bar */}
                    <div className="mt-3">
                      <div className="w-full bg-gray-200 rounded-full h-2">
                        <div
                          className={`h-2 rounded-full transition-all ${comp.sufficient ? 'bg-green-500' : 'bg-red-500'}`}
                          style={{ width: `${progressPercent}%` }}
                        />
                      </div>
                      <p className="text-xs text-gray-500 mt-1">
                        {Math.round(progressPercent)}% available
                      </p>
                    </div>

                    {comp.shortage_info && !isPartialSecond && (
                      <div className="mt-3 p-2 bg-white border border-red-200 rounded text-xs">
                        <p className="font-semibold text-red-700">
                          Shortage: {formatQuantity(comp.shortage_info.shortage_quantity)} {comp.shortage_info.unit}
                        </p>
                        {comp.shortage_info.reason && (
                          <p className="text-gray-600 italic mt-1">{comp.shortage_info.reason}</p>
                        )}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}

            {/* "Show all" button overlaying faded 2nd component */}
            {hasMany && !showAllComponents && (
              <div className="absolute bottom-0 left-0 right-0 flex justify-center pb-4">
                <button
                  onClick={() => setShowAllComponents(true)}
                  className="px-6 py-3 bg-blue-600 hover:bg-blue-700 text-white text-sm font-semibold rounded-lg shadow-lg transition-colors z-20"
                >
                  Show all {mergedComponents.length} components ({mergedComponents.length - 2} more)
                </button>
              </div>
            )}
          </div>

          {/* Show less button */}
          {hasMany && showAllComponents && (
            <button
              onClick={() => setShowAllComponents(false)}
              className="w-full py-3 mt-4 bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm font-semibold rounded-lg transition-colors"
            >
              Show less components
            </button>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProductionSection;
