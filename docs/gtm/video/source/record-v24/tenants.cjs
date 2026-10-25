// Demo workspace data the scenes need, per tenant: PP_TENANT=eg («مطاعم سند», default) or sa («مطاعم رواق»).
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
};
module.exports = T[process.env.PP_TENANT || 'eg'];
