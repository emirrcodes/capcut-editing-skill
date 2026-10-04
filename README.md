# CapCut Editing Skill

Cut silence, cut non-speech with speech detection, and add editable, phrase-based subtitles to a local CapCut Desktop project using your AI agent. Supports video with embedded audio and audio-only projects. No mandatory manual editing step or computer-control tools.

## Give this link to your agent

Open a new local project in **Claude Code, Cursor, or Codex**, then send:

> Install CapCut Editing Skill in this project from https://github.com/emirrcodes/capcut-editing-skill and check that it is ready to use.

**For the installing agent:** download this public repository into a separate package folder; do not overwrite the user's working files. Read skills/capcut-editing/SKILL.md. Run `python install.py --agent claude|cursor|codex --project <user-project-folder>` with the correct agent value. Installation defaults to this project only. Run the installed scripts/setup.py, use its reported virtualenv Python, then run scripts/capcut_tool.py doctor. Check/install FFmpeg through the user's platform package manager if missing. Confirm the discovered skill, speech engine, FFmpeg, and usable font. Respect the host's filesystem/network permissions; report actual missing prerequisites rather than claiming installation succeeded. No GitHub login is needed to download this public package. Bare links do not universally install skills; use the request above.

## Kullanım

```text
“proje adı” sessiz kısımları kes
“proje adı” konuşmasız kısımları kes
“proje adı” altyazı ekle
```

| Komut | Ne yapar? |
| --- | --- |
| **sessiz kısımları kes** | Ses seviyesine göre keser: varsayılan eşik **−30 dBFS**, minimum sessizlik 0.25 saniye. |
| **konuşmasız kısımları kes** | Konuşma modeliyle tarar; kesilecek aralıkları daha hassas ikinci geçişle kontrol eder. “Konuşma olmayan kısımları kes” de bu komutu çalıştırır. |
| **altyazı ekle** | Mevcut timeline'a anlamlı, genellikle 4–6 kelimelik altyazılar ekler. |

Birlikte de isteyebilirsiniz: `“proje adı” konuşmasız kısımları kes ve altyazı ekle` veya `“proje adı” sessiz kısımları kes ve altyazı ekle`.

Agent, mevcut CapCut timeline'ını okur; birleşik istekte kesim ve altyazıyı birlikte hazırlar, doğrular ve uygular. Arada manuel kontrol zorunlu değildir. Sonuç CapCut içinde düzenlenebilir kalır. Proje adı belirsizse klasör yolunu verin. Yazma sırasında **işlem yapılacak proje kaydedilip kapatılmış olmalı**; CapCut ana ekranda veya başka bir projede açık kalabilir. Agent hedef projenin kapalı olduğunu doğrular; işlemden sonra projeyi yeniden açın. Ekran/klavye/fare kontrolü gerekmez, yerel dosya ve komut erişimi gerekir.

**Konuşmasız kesim ses yüksekliğine göre karar vermez.** Yerel [Silero VAD](https://github.com/snakers4/silero-vad) modeli konuşma bölgelerini bulur. Aday konuşmasız aralıklar çevrelerindeki sesle birlikte tekrar taranır; düşük sesli bölümler analiz sırasında güçlendirilerek de kontrol edilir. İkinci geçişte bulunan olası konuşma korunur. Kelime kenarlarında varsayılan 0.12 saniye pay ve 0.30 saniyeden kısa doğal duraklamalar korunur. Bu, fan/trafik gibi gürültüyü konuşmadan ayırmayı amaçlar; başka konuşmalar veya şarkı da konuşma sayılabilir. Amaçlanan konuşmacıyı tek başına ayırma garantisi yoktur. Hiç konuşma bulunmazsa tüm videoyu silmek yerine işlem durur.

**Yüksek gürültüde ek kelime kontrolü:** Agent `speech_word_review` seçeneğini açarak güncel sesin Whisper kelime zamanlarını VAD ile birlikte inceleyebilir. Zayıf konuşmanın ve kelime içindeki kısa boşlukların korunmasına yardımcı olur. Şüpheli tekrarlı transkripsiyonlar bağımsız olarak yeniden taranır; çözülemeyen aralıklar korunur. Kelime zamanları gürültüye doğru uzayabildiğinden bazen ek konuşmasız ses de korunabilir; uzun veya VAD ile zayıf örtüşen kelime zamanları yerel bağlamda bağımsız yeniden kontrol edilir. Kelime yeniden bulunup daha kısa bir zamanla eşleşirse beklemeyi kapsayan süre daraltılır; belirsiz kelime korunur. Belirli bir aralıkta konuşma olmadığını söylerseniz agent bunu yalnızca mevcut proje sürümüne bağlı bir inceleme kararı olarak uygulayabilir. Bu inceleme altyazı eklemez; yerel transkripsiyon modeli gerektirir. “Konuşmalar arasındaki kısa duraklamaları da kaldır; konuşmaları, tekrarları ve yarım başlayan cümleleri koru” diyebilirsiniz. Agent 80 ms kalan duraklama, 30 ms konuşma kenarı payı ve 80 ms minimum konuşma başlangıç ayarlarıyla daha sıkı bir hazırlık yapar; kelime korumasını ve kesilmiş sesi yeniden transkribe ederek kaynak aralığı kontrolünü açık tutar. Bunlar kayda göre revize edilen başlangıç ayarlarıdır. Eksilen bir transkripsiyon kelimesi tek başına sesin silindiği anlamına gelmez. 100 ms minimum klip uzunluğu, duraklama tespit eşiğinden ayrıdır. Konuşulan tekrarları veya yanlış başlangıçları temizlemek ayrı bir istektir.

Kısa duraklamaları da kaldırmak istediğinizde agent tüm mevcut timeline’ı örtüşen konuşma taramalarıyla kontrol eder. Uzayan kelime zamanlarının sakladığı boşluklarda, boşluğun iki tarafını ayrıca transkribe ederek kelimenin yerini doğrular. Belirsiz heceler, tekrarlar ve konuşma olarak algılanan bölgeler korunur; raporda hangi aralıkların neden kaldığı görülebilir.

Varsayılan altyazılar Türkçe, küçük harf, beyaz ve siyah konturludur. Anlamlı bloklar genellikle **4–6 kelime**, en fazla 6 kelimedir; kısa tam ifadeler daha kısa olabilir. Altyazılar boşluksuz ilerler. Klip sınırları iki yönde kontrol edilir: soldaki metin sağ klibe taşmamalı, sağdaki metin solda erken görünmemelidir. İki konuşma bloğu arasındaki boşlukta video kesimi varsa iki altyazı tam kesimde buluşur; sağ kelimenin biraz sonra başlaması soldaki metni uzatmak için gerekçe değildir. Aynı klip içindeki boşluklar doğal kelime başlangıcına kadar doldurulur. Erken zamanlanmış sağ kelime için 0.25 saniyelik kesim hizalaması da korunur. Konuşma klipler arasında devam ediyorsa doğal ifade sınırları korunur; birden fazla aday kesim veya belirsiz sahiplik ayrıca incelenir.

Kelime sayısı, dil, büyük/küçük harf, noktalama, font, boyut, renk, konum, sessizlik ve konuşma algılama ayarları değiştirilebilir. Agentınıza tercihinizi söyleyin; references/config.example.json üzerinden dışarıda bir ayar dosyası oluşturabilir. Kullanıcı tercihleri varsayılanların önündedir.

**Sessizlik kesme ses seviyesine dayanır:** FFmpeg `silencedetect=noise=-30dB:d=0.25`; arası ≤0.12 saniye sessizlikler birleştirilir, <0.10 saniye kalan parçalar atılır. Ortam gürültüsü varsa gürültülü konuşmasız bölümleri kaçırabilir; eşiği yükseltmek alçak sesli konuşmayı da kesebilir. Böyle kayıtlarda konuşmasız kesim komutunu tercih edebilirsiniz.

**Ortam sesine göre agentla konuşarak revize edebilirsiniz.** Fan, trafik, müzik veya mikrofon dip sesi olduğunu söyleyin; gerekirse kesilecek aralıkları daha detaylı incelemesini isteyin. Agent seçilen yöntemin eşiğini, kelime kenarı paylarını ve kısa duraklamaların korunmasını kayda göre değerlendirebilir. İlk sonuç fazla sert veya fazla temkinliyse yedekten geri dönüp yeni ayarlarla hazırlamasını isteyebilirsiniz. Tek bir ayar her ortama uymaz.

```text
“Bu kayıtta fan sesi var; konuşmasız kısımları kes, şüpheli aralıkları detaylı incele”
“Ortam sesi çok yüksek; VAD ile kelime zamanlarını birlikte kontrol et”
“Konuşma uçlarını koruyarak daha kısa duraklamaları da kes”
“Kelime sonları fazla kesiliyor; daha temkinli ayarlarla yeniden hazırla”
“Kısa doğal duraklamaları koru, uzun sessizlikleri kes”
```

## Platforms and installation

- **Apple Silicon macOS:** MLX Whisper, or faster-whisper on CPU.
- **Windows / Intel macOS:** faster-whisper; CPU is the default, NVIDIA/CUDA optional. Windows path handling, installation and transcription adaptation are included; **Windows CapCut round-trip verification is pending**.
- Python **3.10+**, FFmpeg, an installed font, and a local agent with file/terminal access are required. A browser-only chatbot without local access cannot edit your local CapCut files.

Setup installs CPU Silero VAD through [faster-whisper](https://github.com/SYSTRAN/faster-whisper), plus MLX Whisper when selected, in an isolated virtualenv. The small VAD model comes with that dependency; speech-only cutting needs no Whisper transcription weights. The transcription model downloads on first caption use. Detection and transcription run locally; model files are not included in this repository. Once a local agent reads the generated transcript, that text is subject to the agent provider's ordinary data handling.

Optional manual download: use **Code → Download ZIP**, extract, then:

```sh
python install.py --agent codex --project /path/to/your/project
# agent values: codex, claude, cursor; on Windows use py -3 if appropriate
```

Use `--scope user` only if you want the skill available across projects. `--replace` preserves the previous installed skill in a timestamped sibling backup. FFmpeg is installed separately. Detailed editing commands and restore instructions are in [workflow.md](skills/capcut-editing/references/workflow.md).

## Supported drafts and backups

Supports readable JSON draft_info.json or draft_content.json layouts and detected full-draft mirrors in a single timeline. All detected full copies must agree before an edit. Cutting supports one forward 1.0x media track and optional previous codex_subtitles. Multi-track cutting, speed ramps, reversed/animated primary clips, transitions, encrypted drafts, and unknown schemas are rejected. Subtitle-only editing preserves user text tracks and replaces only codex_subtitles.

Cutting checks the pieces created at existing clip boundaries, not only global keep ranges. To prevent new clips below 100 ms, it keeps a little extra audio within the same original clip and reports those intervals. Existing short clips stay whole. Direct cutting and final validation reject new or shortened micro-clips; discontinuous source ranges are never joined into one continuous clip to bypass the check.

Every apply/restore creates timestamped backups before project writes. Source fingerprints prevent applying stale work. A failed write attempts recovery; crashes or storage failures may still need restore from the manifest. Keep the reported backup suffix. Temporary audio/transcript files are cleaned after successful apply; the cleanup command handles abandoned preparations. No export/render of the final video is included.

The subtitle template contains schema/style defaults only: no personal project text, paths, footage, font binaries, or account identifiers. Compatibility is constrained by CapCut's changing draft format. Automated tests use synthetic projects; they do not prove compatibility with every CapCut version. This is an independent project, not an official CapCut product.

## Development

```sh
python -m pip install "faster-whisper>=1.2.1,<2"
python -m unittest discover -s tests -v
python skills/capcut-editing/scripts/capcut_tool.py doctor
```

Tests cover real FFmpeg cuts, bundled VAD rejection of loud noise, weak-word protection, independent checks of suspicious ASR repetitions, three-millisecond clip-boundary regressions, preserved existing short clips, post-write validation/rollback, separate speech/caption modes, caption timing, stale-plan refusal, alternate layouts, and all three agent installers. Transcription adapters are tested without downloading Whisper weights. Native CapCut/Windows round trips should be recorded separately before changing the compatibility claims.

MIT licensed. See [LICENSE](LICENSE).
