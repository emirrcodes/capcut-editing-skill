# CapCut Editing Skill

Remove silent parts and add editable, phrase-based subtitles to a local CapCut Desktop project using your AI agent. Supports video with embedded audio and audio-only projects. No mandatory manual editing step or computer-control tools.

## Give this link to your agent

Open a new local project in **Claude Code, Cursor, or Codex**, then send:

> Install CapCut Editing Skill in this project from https://github.com/emirrcodes/capcut-editing-skill and check that it is ready to use.

**For the installing agent:** download this public repository into a separate package folder; do not overwrite the user's working files. Read skills/capcut-editing/SKILL.md. Run `python install.py --agent claude|cursor|codex --project <user-project-folder>` with the correct agent value. Installation defaults to this project only. Run the installed scripts/setup.py, use its reported virtualenv Python, then run scripts/capcut_tool.py doctor. Check/install FFmpeg through the user's platform package manager if missing. Confirm the discovered skill, speech engine, FFmpeg, and usable font. Respect the host's filesystem/network permissions; report actual missing prerequisites rather than claiming installation succeeded. No GitHub login is needed to download this public package. Bare links do not universally install skills; use the request above.

## Kullanım

```text
“proje adı” sessiz kısımları kes ve altyazı ekle
“proje adı” konuşma olmayan kısımları kes ve altyazı ekle
“proje adı” sessiz kısımları kes
“proje adı” konuşma olmayan kısımları kes
“proje adı” altyazı ekle
```

Agent, mevcut CapCut timeline'ını okur; birleşik istekte kesim ve altyazıyı birlikte hazırlar, doğrular ve uygular. Arada manuel kontrol zorunlu değildir. Sonuç CapCut içinde düzenlenebilir kalır. Proje adı belirsizse klasör yolunu verin. Yazma sırasında **CapCut kapalı olmalı**; sonra projeyi yeniden açın. Ekran/klavye/fare kontrolü gerekmez, yerel dosya ve komut erişimi gerekir.

“Konuşma olmayan kısımları kes” de aynı kesme isteğinin doğal bir ifade biçimidir. Bu sürümde temel yöntem aşağıda açıklanan ses seviyesi analizidir; bu ifade gürültü altında otomatik konuşma algılama garantisi anlamına gelmez. Ortam sesini agenta tarif ederek yaklaşımı ve ayarları revize edebilirsiniz.

Varsayılan altyazılar Türkçe, küçük harf, beyaz ve siyah konturludur. Anlamlı bloklar genellikle **4–6 kelime**, en fazla 6 kelimedir; kısa tam ifadeler daha kısa olabilir. Altyazılar boşluksuz ilerler. Klip değişiminde sonraki bağlamın metni önceki klipte görünmesin diye, kesimden en fazla 0.25 saniye önce başlayıp kesim sonrasına uzanan ilk kelimenin blok başlangıcı kesime hizalanır. Konuşma klipler arasında devam ediyorsa doğal ifade sınırları korunur.

Kelime sayısı, dil, büyük/küçük harf, noktalama, font, boyut, renk, konum ve sessizlik ayarları değiştirilebilir. Agentınıza tercihinizi söyleyin; references/config.example.json üzerinden dışarıda bir ayar dosyası oluşturabilir. Kullanıcı tercihleri varsayılanların önündedir.

**Sessizlik kesme ses seviyesine dayanır:** FFmpeg `silencedetect=noise=-30dB:d=0.25`; arası ≤0.12 saniye sessizlikler birleştirilir, <0.10 saniye kalan parçalar atılır. Sessiz ortamda konuşma videoları için tasarlanmıştır. Ortam gürültüsü varsa agentınıza söyleyin: gürültülü konuşmasız bölümleri kaçırabilir; eşiği yükseltmek alçak sesli konuşmayı da kesebilir. Bu sürüm konuşma algılayan bir kesici olduğunu iddia etmez.

**Ortam sesine göre agentla konuşarak revize edebilirsiniz.** Fan, trafik, müzik veya mikrofon dip sesi olduğunu söyleyin; gerekirse kısa bir ses örneğini incelemesini isteyin. Agent sessizlik eşiğini, minimum sessizlik süresini ve kısa parçaların korunmasını kayda göre değerlendirebilir. İlk sonuç fazla sert veya fazla temkinliyse yedekten geri dönüp yeni ayarlarla hazırlamasını isteyebilirsiniz. Tek bir ayar her ortama uymaz; ses seviyesine dayalı yöntem bazı gürültülü kayıtlarda yeterli olmayabilir.

```text
“Bu kayıtta fan sesi var; sessizlik ayarlarını sesi inceleyerek revize et”
“Kelime sonları fazla kesiliyor; daha temkinli ayarlarla yeniden hazırla”
“Kısa doğal duraklamaları koru, uzun sessizlikleri kes”
```

## Platforms and installation

- **Apple Silicon macOS:** MLX Whisper, or faster-whisper on CPU.
- **Windows / Intel macOS:** faster-whisper; CPU is the default, NVIDIA/CUDA optional. Windows path handling, installation and transcription adaptation are included; **Windows CapCut round-trip verification is pending**.
- Python **3.10+**, FFmpeg, an installed font, and a local agent with file/terminal access are required. A browser-only chatbot without local access cannot edit your local CapCut files.

Only the chosen speech engine is installed in an isolated virtualenv. The model downloads on first use; transcription inference runs locally. Model files are not included in the repository. Once a local agent reads the generated transcript, that text is subject to the agent provider's ordinary data handling; this package does not promise that the entire agent conversation stays offline.

Optional manual download: use **Code → Download ZIP**, extract, then:

```sh
python install.py --agent codex --project /path/to/your/project
# agent values: codex, claude, cursor; on Windows use py -3 if appropriate
```

Use `--scope user` only if you want the skill available across projects. `--replace` preserves the previous installed skill in a timestamped sibling backup. FFmpeg is installed separately. Detailed editing commands and restore instructions are in [workflow.md](skills/capcut-editing/references/workflow.md).

## Supported drafts and backups

Supports readable JSON draft_info.json or draft_content.json layouts and detected full-draft mirrors in a single timeline. All detected full copies must agree before an edit. Cutting supports one forward 1.0x media track and optional previous codex_subtitles. Multi-track cutting, speed ramps, reversed/animated primary clips, transitions, encrypted drafts, and unknown schemas are rejected. Subtitle-only editing preserves user text tracks and replaces only codex_subtitles.

Every apply/restore creates timestamped backups before project writes. Source fingerprints prevent applying stale work. A failed write attempts recovery; crashes or storage failures may still need restore from the manifest. Keep the reported backup suffix. Temporary audio/transcript files are cleaned after successful apply; the cleanup command handles abandoned preparations. No export/render of the final video is included.

The subtitle template contains schema/style defaults only: no personal project text, paths, footage, font binaries, or account identifiers. Compatibility is constrained by CapCut's changing draft format. Automated tests use synthetic projects; they do not prove compatibility with every CapCut version. This is an independent project, not an official CapCut product.

## Development

```sh
python -m unittest discover -s tests -v
python skills/capcut-editing/scripts/capcut_tool.py doctor
```

Tests cover real FFmpeg cuts on generated audio, audio-only drafts, native-caption schema and hard-cut timing, preserved user tracks, stale-plan refusal, backup recovery/restore, alternate draft layouts, and installation for all three agents. Speech-engine adapters are tested without downloading models. Native CapCut/Windows round trips should be recorded separately before changing the compatibility claims.

MIT licensed. See [LICENSE](LICENSE).
