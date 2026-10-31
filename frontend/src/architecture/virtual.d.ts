declare module "virtual:architecture-integrity" {
  const hashes: Record<string, string>;
  export default hashes;
  export const assetUrls: Record<string, string>;
  export const publicUrls: { evidence: string; license: string };
}
