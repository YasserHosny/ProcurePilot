// Demo workspace profiles for setup_workspace.cjs and send_rfq.cjs (PP_PROFILE=sa | sa-en | ie).
// sa: «مطاعم رواق» (PPS-39). sa-en: Rawaq Restaurant Group, all-English Saudi demo (PPS-64).
// ie: Liffey Kitchen Group, all-English eurozone demo in Ireland (PPS-65). All names and numbers are fictional.
// Supplier contact addresses are Gmail plus-aliases <owner>+<aliasPrefix><key>@gmail.com, owner given at run time.

// [name, base unit, pack_count, unit_size]
const SA_PRODUCTS_EN = [
  ['Basmati Rice (10 kg bag)', 'kilogram', 1, '10'],
  ['Sunflower Oil (18 L tin)', 'litre', 1, '18'],
  ['Chilled Chicken (10 kg carton)', 'kilogram', 1, '10'],
  ['Tomatoes (6 kg carton)', 'kilogram', 1, '6'],
  ['Red Onions (20 kg bag)', 'kilogram', 1, '20'],
  ['Potatoes (20 kg bag)', 'kilogram', 1, '20'],
  ['Cucumbers (5 kg carton)', 'kilogram', 1, '5'],
  ['Lemons (5 kg carton)', 'kilogram', 1, '5'],
  ['Fresh Lamb', 'kilogram', 1, '1'],
  ['White Sugar (10 kg bag)', 'kilogram', 1, '10'],
  ['Flour (45 kg bag)', 'kilogram', 1, '45'],
  ['UHT Milk (12 × 1 L)', 'litre', 12, '1'],
  ['Yoghurt (12 × 1 kg)', 'kilogram', 12, '1'],
  ['Eggs (tray of 30)', 'each', 1, '30'],
  ['White Cheese (16 kg tin)', 'kilogram', 1, '16'],
  ['Samoli Bread (bag of 50)', 'each', 1, '50'],
  ['Aluminium Containers (carton of 500)', 'each', 1, '500'],
  ['Paper Cups (carton of 1,000)', 'each', 1, '1000'],
  ['Dishwashing Liquid (20 L)', 'litre', 1, '20'],
  ['Drinking Water (40 × 330 ml)', 'millilitre', 40, '330'],
];

const IE_PRODUCTS = [
  ['Basmati Rice (10 kg bag)', 'kilogram', 1, '10'],
  ['Sunflower Oil (20 L drum)', 'litre', 1, '20'],
  ['Chicken Breast (5 kg box)', 'kilogram', 1, '5'],
  ['Tomatoes (6 kg box)', 'kilogram', 1, '6'],
  ['Brown Onions (20 kg sack)', 'kilogram', 1, '20'],
  ['Potatoes (25 kg sack)', 'kilogram', 1, '25'],
  ['Carrots (10 kg sack)', 'kilogram', 1, '10'],
  ['Lemons (5 kg box)', 'kilogram', 1, '5'],
  ['Irish Beef Mince (5 kg)', 'kilogram', 1, '5'],
  ['Caster Sugar (10 kg bag)', 'kilogram', 1, '10'],
  ['Plain Flour (16 kg bag)', 'kilogram', 1, '16'],
  ['Whole Milk (12 × 1 L)', 'litre', 12, '1'],
  ['Natural Yoghurt (6 × 1 kg)', 'kilogram', 6, '1'],
  ['Free-range Eggs (tray of 30)', 'each', 1, '30'],
  ['Irish Cheddar (5 kg block)', 'kilogram', 1, '5'],
  ['Sourdough Loaves (box of 12)', 'each', 1, '12'],
  ['Compostable Containers (box of 500)', 'each', 1, '500'],
  ['Paper Cups (box of 1,000)', 'each', 1, '1000'],
  ['Dishwashing Liquid (20 L)', 'litre', 1, '20'],
  ['Still Water (24 × 500 ml)', 'millilitre', 24, '500'],
];

module.exports = {
  sa: {
    tenant: 'مطاعم رواق', currency: 'SAR', ns: 'procurepilot-sa-demo', aliasPrefix: 'pp-sa-',
    branches: [
      { key: 'olaya', name: 'فرع العليا', address: 'حي العليا، الرياض', region: 'SA' },
      { key: 'malqa', name: 'فرع الملقا', address: 'حي الملقا، الرياض', region: 'SA' },
      { key: 'tahlia', name: 'فرع التحلية', address: 'شارع التحلية، جدة', region: 'SA' },
    ],
    costCentres: [
      { key: 'olaya', name: 'المطبخ — العليا', code: 'KIT-OLY' },
      { key: 'malqa', name: 'المطبخ — الملقا', code: 'KIT-MLQ' },
      { key: 'tahlia', name: 'المطبخ — جدة', code: 'KIT-JED' },
    ],
    budget: '60000', guardrailLimit: '10000',
    suppliers: [
      { key: 'dhahabi', name: 'الذهبي للتموين', payment_terms: 'الدفع خلال 30 يومًا', lead_time_days: 2 },
      { key: 'wafra', name: 'الوفرة للمواد الغذائية', payment_terms: 'الدفع خلال 30 يومًا', lead_time_days: 3 },
      { key: 'qassim', name: 'خضار القصيم الطازجة', payment_terms: 'الدفع عند الاستلام', lead_time_days: 1 },
    ],
    products: [
      ['أرز بسمتي (كيس 10 كجم)', 'kilogram', 1, '10'], ['زيت دوار الشمس (تنكة 18 لتر)', 'litre', 1, '18'],
      ['دجاج مبرد (كرتون 10 كجم)', 'kilogram', 1, '10'], ['طماطم (كرتون 6 كجم)', 'kilogram', 1, '6'],
      ['بصل أحمر (كيس 20 كجم)', 'kilogram', 1, '20'], ['بطاطس (كيس 20 كجم)', 'kilogram', 1, '20'],
      ['خيار (كرتون 5 كجم)', 'kilogram', 1, '5'], ['ليمون (كرتون 5 كجم)', 'kilogram', 1, '5'],
      ['لحم غنم طازج', 'kilogram', 1, '1'], ['سكر أبيض (كيس 10 كجم)', 'kilogram', 1, '10'],
      ['دقيق (كيس 45 كجم)', 'kilogram', 1, '45'], ['حليب طويل الأجل (كرتون 12 × 1 لتر)', 'litre', 12, '1'],
      ['زبادي (كرتون 12 × 1 كجم)', 'kilogram', 12, '1'], ['بيض (كرتون 30 حبة)', 'each', 1, '30'],
      ['جبنة بيضاء (تنكة 16 كجم)', 'kilogram', 1, '16'], ['خبز صامولي (كيس 50 حبة)', 'each', 1, '50'],
      ['علب ألومنيوم للتغليف (كرتون 500 حبة)', 'each', 1, '500'], ['أكواب ورقية (كرتون 1000 حبة)', 'each', 1, '1000'],
      ['سائل غسيل أطباق (جالون 20 لتر)', 'litre', 1, '20'], ['مياه شرب (كرتون 40 × 330 مل)', 'millilitre', 40, '330'],
    ],
    rfqLines: [['زيت دوار الشمس (تنكة 18 لتر)', 10], ['أرز بسمتي (كيس 10 كجم)', 30], ['طماطم (كرتون 6 كجم)', 20]],
    terms: 'التوريد لفرع العليا. الدفع خلال 30 يومًا من الاستلام. الأسعار شاملة ضريبة القيمة المضافة 15%.',
  },
  'sa-en': {
    tenant: 'Rawaq Restaurant Group', currency: 'SAR', ns: 'procurepilot-sa-en-demo', aliasPrefix: 'pp-sa-en-',
    branches: [
      { key: 'olaya', name: 'Olaya Branch', address: 'Olaya District, Riyadh', region: 'SA' },
      { key: 'malqa', name: 'Al Malqa Branch', address: 'Al Malqa District, Riyadh', region: 'SA' },
      { key: 'tahlia', name: 'Tahlia Branch', address: 'Tahlia Street, Jeddah', region: 'SA' },
    ],
    costCentres: [
      { key: 'olaya', name: 'Kitchen — Olaya', code: 'KIT-OLY' },
      { key: 'malqa', name: 'Kitchen — Al Malqa', code: 'KIT-MLQ' },
      { key: 'tahlia', name: 'Kitchen — Jeddah', code: 'KIT-JED' },
    ],
    budget: '60000', guardrailLimit: '10000',
    suppliers: [
      { key: 'golden', name: 'Golden Crescent Foodstuff', payment_terms: 'Net 30 days', lead_time_days: 2 },
      { key: 'redsea', name: 'Red Sea Food Trading', payment_terms: 'Net 30 days', lead_time_days: 3 },
      { key: 'qassim', name: 'Qassim Fresh Produce', payment_terms: 'Cash on delivery', lead_time_days: 1 },
    ],
    products: SA_PRODUCTS_EN,
    rfqLines: [['Sunflower Oil (18 L tin)', 10], ['Basmati Rice (10 kg bag)', 30], ['Tomatoes (6 kg carton)', 20]],
    terms: 'Delivery to the Olaya Branch. Payment within 30 days of receipt. Prices include 15% VAT.',
  },
  ie: {
    tenant: 'Liffey Kitchen Group', currency: 'EUR', ns: 'procurepilot-ie-demo', aliasPrefix: 'pp-ie-',
    branches: [
      { key: 'templebar', name: 'Temple Bar', address: 'Temple Bar, Dublin 2', region: 'IE' },
      { key: 'grandcanal', name: 'Grand Canal Dock', address: 'Grand Canal Dock, Dublin 4', region: 'IE' },
      { key: 'cork', name: 'Cork City Centre', address: 'Oliver Plunkett Street, Cork', region: 'IE' },
    ],
    costCentres: [
      { key: 'templebar', name: 'Kitchen — Temple Bar', code: 'KIT-TMB' },
      { key: 'grandcanal', name: 'Kitchen — Grand Canal', code: 'KIT-GCD' },
      { key: 'cork', name: 'Kitchen — Cork', code: 'KIT-CRK' },
    ],
    budget: '15000', guardrailLimit: '3000',
    suppliers: [
      { key: 'brennan', name: 'Brennan & Walsh Wholesale', payment_terms: 'Net 30 days', lead_time_days: 2 },
      { key: 'atlantic', name: 'Atlantic Fresh Foods Ltd', payment_terms: 'Net 30 days', lead_time_days: 3 },
      { key: 'kerrigan', name: 'Kerrigan Farm Produce', payment_terms: 'Net 14 days', lead_time_days: 1 },
    ],
    products: IE_PRODUCTS,
    rfqLines: [['Sunflower Oil (20 L drum)', 10], ['Basmati Rice (10 kg bag)', 30], ['Tomatoes (6 kg box)', 20]],
    terms: 'Delivery to Temple Bar. Payment within 30 days of invoice. Prices exclude VAT; food items are zero-rated.',
  },
};
