import MultiAnalyzeClient from "./MultiAnalyzeClient";

type Props = {
  searchParams: Promise<{ items?: string }>;
};

export default async function MultiAnalyzePage({ searchParams }: Props) {
  const { items } = await searchParams;
  return <MultiAnalyzeClient itemsParam={items || ""} />;
}
