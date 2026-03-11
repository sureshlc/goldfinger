"use client";

import React, { useState } from "react";
import { CheckCircle2, XCircle, Package, AlertTriangle, Layers } from "lucide-react";
import InventorySection from "./InventorySection";
import type { InventoryLevel } from "./InventorySection";
import ProductionSection from "./ProductionSection";
import type { ProductionAnalysisResponse } from "./ProductionSection";

interface ItemDetailsProps {
  sku: string;
  name: string;
  inventoryData?: InventoryLevel | null;
  productionData?: ProductionAnalysisResponse | null;
  desiredQuantity: number;
}

/**
 * Main item details component
 * Removed BOMSection - BOM now shown within ProductionSection
 */
const ItemDetails: React.FC<ItemDetailsProps> = ({
  sku,
  name,
  inventoryData,
  productionData,
  desiredQuantity,
}) => {
  const [isExpanded, setAllExpanded] = useState(false);

  const availableSections = {
    inventory: !!inventoryData,
    production: !!productionData,
  };

  const hasAnySection = Object.values(availableSections).some(Boolean);

  const shortageCount = productionData?.shortages?.length ?? 0;
  const componentCount = productionData?.bom_components?.length ?? 0;

  return (
    <div>
      {/* Page Header */}
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900">
          {sku}{" "}
          <span className="text-gray-400 font-normal text-lg">
            {name ? `— ${name.trim()}` : ""}
          </span>
        </h1>
        {hasAnySection && (
          <button
            onClick={() => setAllExpanded(!isExpanded)}
            className="px-3 py-1.5 text-sm font-medium text-blue-600 border border-blue-300 rounded-lg hover:bg-blue-50 transition"
          >
            {isExpanded ? "Collapse All" : "Expand All"}
          </button>
        )}
      </div>

      {/* KPI Dashboard */}
      {productionData && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
          {/* Card 1: Production Status */}
          <div className={`rounded-xl border p-4 ${productionData.can_produce ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200'}`}>
            <div className="flex items-center gap-2 mb-2">
              {productionData.can_produce
                ? <CheckCircle2 className="w-5 h-5 text-green-600" />
                : <XCircle className="w-5 h-5 text-red-600" />
              }
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Production</p>
            </div>
            <p className={`text-lg font-bold ${productionData.can_produce ? 'text-green-700' : 'text-red-700'}`}>
              {productionData.can_produce ? "Can Produce" : "Cannot Produce"}
            </p>
          </div>

          {/* Card 2: Max Producible */}
          <div className="rounded-xl border border-blue-200 bg-blue-50 p-4">
            <div className="flex items-center gap-2 mb-2">
              <Package className="w-5 h-5 text-blue-600" />
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Max Producible</p>
            </div>
            <p className="text-2xl font-bold text-blue-700">{productionData.max_quantity_producible}</p>
          </div>

          {/* Card 3: Total Components */}
          <div className="rounded-xl border border-gray-200 bg-white p-4">
            <div className="flex items-center gap-2 mb-2">
              <Layers className="w-5 h-5 text-gray-500" />
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Components</p>
            </div>
            <p className="text-2xl font-bold text-gray-900">{componentCount}</p>
          </div>

          {/* Card 4: Shortages */}
          <div className={`rounded-xl border p-4 ${shortageCount > 0 ? 'bg-red-50 border-red-200' : 'bg-green-50 border-green-200'}`}>
            <div className="flex items-center gap-2 mb-2">
              <AlertTriangle className={`w-5 h-5 ${shortageCount > 0 ? 'text-red-500' : 'text-green-500'}`} />
              <p className="text-xs font-medium text-gray-500 uppercase tracking-wide">Shortages</p>
            </div>
            <p className={`text-2xl font-bold ${shortageCount > 0 ? 'text-red-700' : 'text-green-700'}`}>{shortageCount}</p>
          </div>
        </div>
      )}

      {/* Sections */}
      {productionData ? (
        <ProductionSection
          productionData={productionData}
          currentQuantity={desiredQuantity}
          sku={sku}
          isExpanded={isExpanded}
        />
      ) : (
        <p className="italic text-gray-500 mb-4">No production data available.</p>
      )}

      {inventoryData ? (
        <InventorySection data={inventoryData} />
      ) : (
        <p className="italic text-gray-500 mb-4">No inventory data available.</p>
      )}

      {!hasAnySection && (
        <div className="bg-white rounded-xl shadow border border-gray-200 p-8 text-center">
          <p className="text-gray-500">No detailed data available for this item.</p>
        </div>
      )}
    </div>
  );
};

export default ItemDetails;
