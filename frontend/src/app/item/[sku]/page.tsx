import ItemDetailClient from "./ItemDetailClient";

type Props = {
  params: Promise<{ sku: string }>;
  searchParams: Promise<{ quantity?: string }>;
};

export default async function ItemDetailPage({ params, searchParams }: Props) {
  const { sku } = await params;
  const { quantity } = await searchParams;
  return <ItemDetailClient sku={sku} desiredQuantity={parseInt(quantity || "1")} />;
}
