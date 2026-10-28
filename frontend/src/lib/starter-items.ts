/** Common sari-sari items for onboarding step 2; sizes live in `description` (the report's Size column). No prices: they differ per store, so the owner fills them in. */
export type StarterItem = { name: string; description: string; category: string };

export const STARTER_ITEMS: StarterItem[] = [
  { name: "Lucky Me Pancit Canton", description: "60g", category: "Noodles" },
  { name: "Lucky Me Beef Mami", description: "55g", category: "Noodles" },
  { name: "555 Tuna Flakes", description: "155g", category: "Canned goods" },
  { name: "Argentina Corned Beef", description: "150g", category: "Canned goods" },
  { name: "Ligo Sardines", description: "155g", category: "Canned goods" },
  { name: "Coca-Cola", description: "290ml", category: "Drinks" },
  { name: "Kopiko 3in1", description: "25g", category: "Coffee" },
  { name: "Nescafé Classic", description: "2g", category: "Coffee" },
  { name: "Bear Brand Powdered Milk", description: "33g", category: "Milk" },
  { name: "Alaska Evaporated Milk", description: "360ml", category: "Milk" },
  { name: "Silver Swan Soy Sauce", description: "200ml", category: "Condiments" },
  { name: "Datu Puti Vinegar", description: "200ml", category: "Condiments" },
  { name: "Surf Powder Detergent", description: "65g", category: "Household" },
  { name: "Safeguard Soap", description: "60g", category: "Household" },
  { name: "Skyflakes Crackers", description: "25g", category: "Snacks" },
];
