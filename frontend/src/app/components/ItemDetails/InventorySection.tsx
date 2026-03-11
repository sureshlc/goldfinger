"use client";

import React from "react";

export interface InventoryLevel {
  item_id: string;
  item_name: string;
  item_sku: string;
  available_quantity: number;
  inventory_status?: string;
  location_name?: string;
}

interface InventorySectionProps {
  data: InventoryLevel;
}

const InventorySection: React.FC<InventorySectionProps> = ({ data }) => {
  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden mb-6">
      <div className="px-6 py-4 border-b border-gray-100 bg-gray-50">
        <h2 className="text-sm font-semibold text-gray-700 uppercase tracking-wide">
          Finished Good Inventory
        </h2>
      </div>
      <div className="p-6">
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div>
            <p className="text-xs text-gray-500 mb-1">Item Name</p>
            <p className="text-sm font-semibold text-gray-900">{data.item_name}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">SKU</p>
            <p className="text-sm font-semibold text-gray-900">{data.item_sku}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Available Quantity</p>
            <p className="text-lg font-bold text-blue-600">{data.available_quantity}</p>
          </div>
          <div>
            <p className="text-xs text-gray-500 mb-1">Location</p>
            <p className="text-sm font-semibold text-gray-900">{data.location_name || "All"}</p>
          </div>
        </div>
        {data.inventory_status && (
          <div className="mt-4 pt-4 border-t border-gray-100">
            <p className="text-xs text-gray-500 mb-1">Status</p>
            <p className="text-sm font-semibold text-gray-900">{data.inventory_status}</p>
          </div>
        )}
      </div>
    </div>
  );
};

export default InventorySection;
