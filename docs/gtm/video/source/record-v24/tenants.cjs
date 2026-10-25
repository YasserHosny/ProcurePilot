// Demo workspace data the scenes need, per tenant: PP_TENANT=eg («مطاعم سند», default), sa («مطاعم رواق»), sa-en (Rawaq Restaurant Group) or ie (Liffey Kitchen Group).
const T = {
  eg: {
    name: 'مطاعم سند',
    lines: [['زيت عباد الشمس (صفيحة 18 لتر)', '8'], ['أرز مصري (شيكارة 25 كجم)', '12'], ['بصل أبيض', '80']],
    suppliers: ['النور للمواد الغذائية', 'الأمانة للتجارة', 'الحاج سيد للخضار'],
    winner: 'الأمانة للتجارة', runnerUp: 'النور للمواد الغذائية',
    compareProduct: 'زيت عباد الشمس (صفيحة 18 لتر)', compareQty: '8',
    costCentre: 'المطبخ — المعادي',
    ledgerRows: ['زيت عباد الشمس', 'أرز مصري', 'بصل أبيض'],
    terms: { ar: 'التوريد لفرع المعادي. الدفع خلال 30 يومًا من الاستلام.', en: 'Delivery to the Maadi branch. Payment within 30 days of receipt.' },
  },
  sa: {
    name: 'مطاعم رواق',
    lines: [['زيت دوار الشمس (تنكة 18 لتر)', '10'], ['أرز بسمتي (كيس 10 كجم)', '30'], ['طماطم (كرتون 6 كجم)', '20']],
    suppliers: ['الذهبي للتموين', 'الوفرة للمواد الغذائية', 'خضار القصيم الطازجة'],
    winner: 'الذهبي للتموين', runnerUp: 'الوفرة للمواد الغذائية',
    compareProduct: 'زيت دوار الشمس (تنكة 18 لتر)', compareQty: '10',
    costCentre: 'المطبخ — العليا',
    ledgerRows: ['زيت دوار الشمس', 'أرز بسمتي', 'طماطم'],
    terms: { ar: 'التوريد لفرع العليا. الدفع خلال 30 يومًا من الاستلام. الأسعار شاملة ضريبة القيمة المضافة 15%.', en: 'Delivery to the Olaya branch. Payment within 30 days of receipt. Prices include 15% VAT.' },
  },
  'sa-en': {
    name: 'Rawaq Restaurant Group',
    lines: [['Sunflower Oil (18 L tin)', '10'], ['Basmati Rice (10 kg bag)', '30'], ['Tomatoes (6 kg carton)', '20']],
    suppliers: ['Golden Crescent Foodstuff', 'Red Sea Food Trading', 'Qassim Fresh Produce'],
    winner: 'Golden Crescent Foodstuff', runnerUp: 'Red Sea Food Trading',
    compareProduct: 'Sunflower Oil (18 L tin)', compareQty: '10',
    costCentre: 'Kitchen — Olaya',
    ledgerRows: ['Sunflower Oil', 'Basmati Rice', 'Tomatoes'],
    terms: { ar: 'Delivery to the Olaya Branch. Payment within 30 days of receipt. Prices include 15% VAT.', en: 'Delivery to the Olaya Branch. Payment within 30 days of receipt. Prices include 15% VAT.' },
  },
  ie: {
    name: 'Liffey Kitchen Group',
    lines: [['Sunflower Oil (20 L drum)', '10'], ['Basmati Rice (10 kg bag)', '30'], ['Tomatoes (6 kg box)', '20']],
    suppliers: ['Brennan & Walsh Wholesale', 'Atlantic Fresh Foods Ltd', 'Kerrigan Farm Produce'],
    winner: 'Brennan & Walsh Wholesale', runnerUp: 'Atlantic Fresh Foods Ltd',
    compareProduct: 'Sunflower Oil (20 L drum)', compareQty: '10',
    costCentre: 'Kitchen — Temple Bar',
    ledgerRows: ['Sunflower Oil', 'Basmati Rice', 'Tomatoes'],
    terms: { ar: 'Delivery to Temple Bar. Payment within 30 days of invoice. Prices exclude VAT; food items are zero-rated.', en: 'Delivery to Temple Bar. Payment within 30 days of invoice. Prices exclude VAT; food items are zero-rated.' },
  },
};
module.exports = T[process.env.PP_TENANT || 'eg'];
