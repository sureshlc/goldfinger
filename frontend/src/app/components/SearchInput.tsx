"use client";

import React, { KeyboardEvent, ChangeEvent } from "react";

interface SearchInputProps {
  onSelect: (sku: string) => void;
  placeholder?: string;
  query: string;
  setQuery: React.Dispatch<React.SetStateAction<string>>;
  // These props kept for backward compatibility but not used
  fetchSuggestions?: () => Promise<unknown[]>;
  minQueryLength?: number;
}

/**
 * Simplified exact SKU search input
 * User enters SKU (case-insensitive) - converted to uppercase before sending to backend
 */
const SearchInput: React.FC<SearchInputProps> = ({
  onSelect,
  placeholder = "Enter exact SKU",
  query,
  setQuery,
}) => {
  const handleSearch = () => {
    const trimmedQuery = query.trim().toUpperCase(); // Convert to uppercase
    if (trimmedQuery) {
      onSelect(trimmedQuery);
    }
  };

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSearch();
    }
  };

  const onChange = (e: ChangeEvent<HTMLInputElement>) => {
    // Allow user to type in any case, we'll convert on submit
    setQuery(e.target.value);
  };

  return (
    <input
      type="text"
      className="w-full bg-transparent border-none outline-none text-sm text-gray-900 placeholder-gray-400 py-1"
      placeholder={placeholder}
      value={query}
      onChange={onChange}
      onKeyDown={onKeyDown}
    />
  );
};

export default SearchInput;