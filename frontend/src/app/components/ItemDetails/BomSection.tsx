"use client";

import React, { useState, useEffect } from "react";

interface BOMComponent {
  item_id: string;
  item_name: string;
  item_sku: string;
  quantity_required: number;
  unit: string;
  level: number; // add level for indentation
}

export interface BOMResponse {
  parent_item_sku: string;
  components: BOMComponent[];
  total_components: number;
}

interface BOMSectionProps {
  bomData: BOMResponse;
  isExpanded?: boolean;
}

const INDENT_PER_LEVEL = 20; // px

const BOMSection: React.FC<BOMSectionProps> = ({ bomData, isExpanded }) => {
  const [isOpen, setIsOpen] = useState(isExpanded ?? false);

  useEffect(() => {
    if (typeof isExpanded === "boolean") {
      setIsOpen(isExpanded);
    }
  }, [isExpanded]);

  return (
    <div className="border rounded mb-4">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="w-full px-4 py-2 text-left bg-gray-200 font-semibold hover:bg-gray-300"
      >
        Bill of Materials (BOM) - {bomData.total_components} components{" "}
        {isOpen ? "▲" : "▼"}
      </button>

      {isOpen && (
        <div className="p-4">
          {bomData.components.length === 0 ? (
            <p>No components found.</p>
          ) : (
            <ul>
              {bomData.components.map((component) => (
                <li
                  key={component.item_id}
                  className="mb-2 border-b pb-1"
                  style={{ paddingLeft: component.level * INDENT_PER_LEVEL }}
                >
                  <p>
                    <strong>Name:</strong> {component.item_name}
                  </p>
                  <p>
                    <strong>SKU:</strong> {component.item_sku}
                  </p>
                  <p>
                    <strong>Quantity Required:</strong> {component.quantity_required}{" "}
                    {component.unit}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
};

export default BOMSection;
