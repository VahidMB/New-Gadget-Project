# 13) نقشه دیتابیس برای داده‌های داینامیک

## هدف
هر چیزی که ممکن است بعداً توسط WordPress تغییر کند، در دیتابیس سرور اصلی ذخیره شود؛ نه داخل کد.

این سند برای MVP و توسعه بعدی است و جدول‌ها را به‌صورت ماژولار تعریف می‌کند.

---

## 1) `devices`

### نقش
ثبت هر گجت و وضعیت اصلی آن.

### فیلدهای پیشنهادی
- `id`
- `external_id`
- `serial_number`
- `name`
- `plan` → `simple` یا `pro`
- `is_active`
- `ui_version`
- `last_seen_at`
- `created_at`
- `updated_at`

### ارتباط‌ها
- به `device_profiles` وصل می‌شود.
- به `device_updates` وصل می‌شود.
- به `notifications` می‌تواند مقصد باشد.

---

## 2) `device_profiles`

### نقش
تنظیمات اختصاصی هر دستگاه.

### فیلدهای پیشنهادی
- `id`
- `device_id`
- `theme_name`
- `primary_color`
- `secondary_color`
- `background_color`
- `layout_mode`
- `refresh_interval_ms`
- `custom_config`
- `effective_config`
- `updated_at`

### توضیح
`custom_config` چیزی است که از WordPress می‌آید.  
`effective_config` نسخه نهایی است که سرور برای گجت می‌سازد.

### ارتباط‌ها
- یک‌به‌یک با `devices`
- داده‌های `ui_templates` را override می‌کند

---

## 3) `ui_templates`

### نقش
قالب‌های اصلی UI برای `simple` و `pro`.

### فیلدهای پیشنهادی
- `id`
- `name`
- `version`
- `plan_type`
- `default_theme`
- `default_screen`
- `default_rules`
- `is_active`
- `created_at`
- `updated_at`

### توضیح
برای هر پلن می‌توان چند template داشت، ولی یکی باید default باشد.

### ارتباط‌ها
- به `ui_pages` وصل می‌شود.
- به `plan_rules` وابسته است.

---

## 4) `ui_pages`

### نقش
صفحه‌های هر قالب UI.

### فیلدهای پیشنهادی
- `id`
- `template_id`
- `page_key`
- `page_type`
- `priority`
- `refresh_interval_ms`
- `visible_when`
- `is_active`
- `created_at`
- `updated_at`

### توضیح
مثلاً:
- boot
- home
- weather
- market
- news
- custom

### ارتباط‌ها
- یک template چند page دارد.
- هر page چند element دارد.

---

## 5) `ui_elements`

### نقش
اجزای داخل هر page.

### فیلدهای پیشنهادی
- `id`
- `page_id`
- `element_type`
- `label`
- `source_key`
- `x`
- `y`
- `width`
- `height`
- `font_size`
- `color`
- `style`
- `z_index`
- `is_visible`
- `config`

### element_typeهای پیشنهادی
- `text`
- `image`
- `icon`
- `clock`
- `date`
- `weather`
- `price`
- `ticker`
- `chart`

### ارتباط‌ها
- هر page چند element دارد.
- هر element ممکن است به `data_sources` وصل شود.

---

## 6) `data_sources`

### نقش
منابع داده‌ای که UI از آن‌ها تغذیه می‌کند.

### فیلدهای پیشنهادی
- `id`
- `key`
- `name`
- `source_type`
- `base_url`
- `endpoint`
- `auth_type`
- `is_active`
- `priority`
- `cache_ttl_seconds`
- `created_at`
- `updated_at`

### source_typeهای پیشنهادی
- `wordpress`
- `api`
- `scrape`
- `manual`
- `telegram`

### ارتباط‌ها
- به `source_mappings` وصل می‌شود.
- می‌تواند به صفحه یا element خاص داده بدهد.

---

## 7) `source_mappings`

### نقش
تعیین می‌کند هر منبع داده روی کدام page/element استفاده شود.

### فیلدهای پیشنهادی
- `id`
- `source_id`
- `page_id`
- `element_id`
- `mapping_type`
- `transform_config`
- `is_active`
- `created_at`
- `updated_at`

### توضیح
مثلاً `btc_price` از `data_sources` می‌آید و در element نوع `price` روی صفحه `market` نمایش داده می‌شود.

---

## 8) `notifications`

### نقش
ثبت پیام‌ها و اطلاعیه‌ها برای دستگاه‌ها یا مشتری‌ها.

### فیلدهای پیشنهادی
- `id`
- `category`
- `title`
- `message`
- `payload`
- `target_device_id`
- `target_plan`
- `is_delivered`
- `delivery_method`
- `created_at`
- `delivered_at`

### delivery_methodهای پیشنهادی
- `api`
- `mqtt`
- `webhook`
- `local_queue`

### ارتباط‌ها
- ممکن است به یک device خاص یا یک پلن خاص باشد.

---

## 9) `sync_events`

### نقش
ثبت همه تغییرات ورودی از WordPress.

### فیلدهای پیشنهادی
- `id`
- `event_type`
- `entity_type`
- `entity_external_id`
- `source`
- `payload`
- `payload_hash`
- `status`
- `message`
- `created_at`
- `processed_at`

### statusهای پیشنهادی
- `processed`
- `ignored`
- `error`

### اهمیت
برای audit و debug خیلی مهم است.

---

## 10) `firmware_versions`

### نقش
مدیریت نسخه‌های firmware برای OTA.

### فیلدهای پیشنهادی
- `id`
- `version`
- `release_channel`
- `file_url`
- `checksum`
- `signature`
- `min_hardware_version`
- `is_active`
- `release_notes`
- `created_at`
- `updated_at`

### release_channelهای پیشنهادی
- `stable`
- `beta`
- `dev`

---

## 11) `device_updates`

### نقش
ثبت وضعیت OTA هر دستگاه.

### فیلدهای پیشنهادی
- `id`
- `device_id`
- `current_version`
- `target_version`
- `download_status`
- `install_status`
- `error_message`
- `started_at`
- `finished_at`

### download_statusهای پیشنهادی
- `pending`
- `downloading`
- `downloaded`
- `failed`

### install_statusهای پیشنهادی
- `pending`
- `installing`
- `installed`
- `rollback`
- `failed`

---

## 12) `plan_rules`

### نقش
تعیین محدودیت‌های هر پلن.

### فیلدهای پیشنهادی
- `id`
- `plan_name`
- `can_customize_ui`
- `can_change_theme`
- `can_add_pages`
- `can_add_sources`
- `max_pages`
- `max_elements_per_page`
- `max_sources`
- `is_active`
- `created_at`
- `updated_at`

### توضیح
این جدول کمک می‌کند تفاوت `simple` و `pro` فقط در کد نباشد و قابل تغییر از دیتابیس هم باشد.

---

## ارتباط کلی جدول‌ها

```text
devices
  └── device_profiles
        └── ui_templates
              └── ui_pages
                    └── ui_elements
                          └── source_mappings
                                └── data_sources

sync_events ──> devices / data_sources / device_profiles
notifications ──> devices / plan / ui events
firmware_versions ──> device_updates ──> devices
plan_rules ──> ui_templates / device_profiles
```

---

## MVP پیشنهادی

برای شروع فقط این‌ها را بساز:
- `devices`
- `device_profiles`
- `ui_templates`
- `ui_pages`
- `ui_elements`
- `data_sources`
- `sync_events`

بعداً اضافه کن:
- `source_mappings`
- `notifications`
- `firmware_versions`
- `device_updates`
- `plan_rules`

---

## نتیجه عملی

با این مدل:
- UI از کد جدا می‌شود
- WordPress فقط تنظیمات را تغییر می‌دهد
- سرور اصلی نسخه نهایی را می‌سازد
- گجت فقط render می‌کند
