# Düz metin kurulum rehberi

`guide.txt`, https://ahmetemirarslan.com/capcut adresindeki LLM kurulum rehberinin kaynağıdır. HTML, CSS, görsel veya istemci JavaScript'i yoktur. Worker `text/plain; charset=utf-8` döndürür.

Metni değiştirdikten sonra repo kökünden `node website/build.mjs` çalıştırın. `worker.mjs` bu metinden üretilir. Yerel kontrol: `node website/preview.mjs`, ardından http://127.0.0.1:8765/capcut.

Cloudflare Workers'a `worker.mjs` dosyasını ES module olarak yükleyin (`main_module: worker.mjs`). Yalnız şu iki zone route bağlanır:

- `ahmetemirarslan.com/capcut`
- `ahmetemirarslan.com/capcut/*`

Mevcut Cloudflare Pages deploy'u ve DNS kayıtları değiştirilmez. Standart dışı HTTP istemcilerinin Browser Integrity Check nedeniyle 1010 ile engellendiği görüldüğünden, `http_config_settings` aşamasında yalnız şu filtre için `set_config` / `bic: false` kuralı vardır:

```text
(http.host eq "ahmetemirarslan.com" and http.request.uri.path in {"/capcut" "/capcut/" "/capcut/install.txt"} and http.request.method in {"GET" "HEAD"})
```

Global Browser Integrity Check açık kalır; diğer güvenlik ürünleri değişmez. `/capcut`, `/capcut/` ve `/capcut/install.txt` aynı metni döndürür; diğer alt yollar 404, GET/HEAD dışındaki metotlar 405 döndürür. Route dışı bir istek Worker'a ulaşırsa origin'e iletilir.

Yayın sonrası metni, HTTP içerik tipini ve ana sitenin değişmediğini kontrol edin. Bir URL'nin HTTP üzerinden okunabilmesi, her sohbet servisinin o URL'yi mutlaka açacağını garanti etmez. Link açılamıyorsa kullanıcı `guide.txt` metnini sohbetine yapıştırabilir.

API tokenlarını, hesap yapılandırması çıktısını ve kişisel test dosyalarını bu klasöre koymayın. Geri almak için yalnız bu rehbere eklenen iki Worker route'u ve bu rehbere ait `capcut_guide_plaintext_readers` yapılandırma kuralını kaldırın; mevcut Pages sitesi tekrar bu yolları karşılar.
