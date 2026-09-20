# 12) قرارداد UI دستگاه

## هدف
سرور فقط «داده + layout» بفرستد و خود گجت رندر را انجام دهد. این مدل هم امن‌تر است، هم تغییرات آینده UI را ساده‌تر می‌کند.

## اصل طراحی

- **سرور**: تصمیم می‌گیرد چه چیزی و با چه ترتیبی نمایش داده شود.
- **گجت**: همان JSON را می‌خواند و روی LCD رسم می‌کند.
- **کد LCD** از سرور ارسال نمی‌شود.

## فیلدهای اصلی

- `ui_version`: نسخه قرارداد
- `plan`: `simple` یا `pro`
- `theme`: رنگ‌ها و تم کلی
- `screen`: مشخصات صفحه نمایش
- `pages`: فهرست صفحه‌ها
- `elements`: اجزای هر صفحه
- `assets`: منابع تصویر/آیکن
- `rules`: محدودیت‌های هر پلن

## رفتار پلن `simple`

- layout ثابت
- صفحه‌های محدود و از پیش تعریف‌شده
- بدون شخصی‌سازی توسط کاربر
- فقط داده‌های مجاز و ثابت

## رفتار پلن `pro`

- layout قابل تنظیم
- رنگ و صفحه‌ها قابل تغییر از WordPress
- امکان افزودن/حذف page و element
- امکان استفاده از asset سفارشی

## نمونه خروجی مورد انتظار

```json
{
  "ui_version": 1,
  "plan": "pro",
  "theme": {
    "name": "dark",
    "primary_color": "#00B7FF",
    "secondary_color": "#FFFFFF",
    "background_color": "#000000"
  },
  "screen": {
    "orientation": "portrait",
    "width": 320,
    "height": 480,
    "refresh_mode": "manual"
  },
  "pages": [],
  "assets": {},
  "rules": {
    "simple_locked": false,
    "allow_custom_pages": true,
    "allow_custom_theme": true,
    "allow_custom_assets": true
  }
}
```

## نکته اجرایی

برای آینده بهتر است هر `page` این داده‌ها را داشته باشد:

- `id`
- `type`
- `priority`
- `refresh_interval_ms`
- `visible_when`
- `elements`

## خروجی پیشنهادی سرور

بهتر است endpoint نمایش دستگاه همیشه یک payload واحد برگرداند و داخل آن با توجه به پلن، layout مناسب را بسازد. یعنی:

- `simple` → payload ثابت
- `pro` → payload قابل سفارشی‌سازی
