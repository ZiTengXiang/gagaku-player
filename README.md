# Gagaku Score Player (雅楽譜プレイヤー)

日本語の説明は下に記載しています

[![CI](https://github.com/ZiTengXiang/gagaku-player/actions/workflows/ci.yml/badge.svg)](https://github.com/ZiTengXiang/gagaku-player/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/gagaku-player)](https://pypi.org/project/gagaku-player/)

**[English](#english)** | **[日本語](#japanese)**

<a id="english"></a>

## English

A free desktop app for programming (DTM) gagaku, Japanese imperial court music. Type gagaku notation characters (譜字) as plain text and the app plays them as an ensemble of shō, hichiriki, ryūteki, gakubiwa, gakusō, kakko, shōko and taiko (Windows, macOS and Linux; written in Python). No DAW or sample library is needed. It also shows a Western staff view and exports WAV files.

Website (English): https://zitengxiang.github.io/gagaku-player/en/
Website (Japanese): https://zitengxiang.github.io/gagaku-player/

### Install and run

With pip:

```bash
pip install gagaku-player
gagaku-player --demo          # open the sample piece "Wakatake"
gagaku-player piece.gaku      # open a score
```

From source:

```bash
git clone https://github.com/ZiTengXiang/gagaku-player.git
cd gagaku-player
pip install -r requirements.txt
python main.py examples/demo_hyojo.gaku
```

- Requirements: Python 3.10+ and numpy (tkinter ships with Python). You can also start it with `python -m gagaku`.
- On Windows nothing else is needed (playback uses the built-in `winsound`). On macOS/Linux, installing with pip also installs `sounddevice` for playback (from source, run `pip install sounddevice`).
- To launch from an icon on Windows, make a shortcut that runs `pythonw.exe main.py` and set its icon to `gagaku/assets/gagaku.ico` (`pythonw` opens no console window). Rebuild the icon with `python tools/make_icon.py` (needs Pillow and the Yu Mincho font).
- If the app crashes when started without a console, it writes the details to `error.log` and shows a dialog.

### Screen

- Left, "譜面テキスト" (score text) tab: the score editor. While playing, the sounding notes are highlighted in yellow. Lines with errors turn red.
- Left, "楽譜表示" (score view) tab: a read-only full score with the beats of all instruments aligned vertically, five bars per system, all instruments stacked. Bar lines come from `|` in the score; sustained notes are drawn as thin lines. Sounding notes are highlighted during playback; clicking a note selects it in the text (press F6 to play from there).
- Left, "五線譜" (staff) tab: a read-only full score in Western staff notation, five bars per system, with the gagaku character under each note. One beat = a quarter note; notes crossing beats or bar lines are tied. Clefs are chosen automatically from each instrument's range (treble, bass, and treble 8va/8vb). There is no key signature; sharps are written on each note. Shō chords (合竹) are written as chords; biwa sweeps (掻撥) and koto patterns (閑掻・早掻) as arpeggiated chords. Percussion uses a one-line staff (× noteheads for kakko and shōko; tremolo for rolls 来). Highlighting and click-to-jump work as in the score view.
- Top right: a palette of notation characters per instrument. Click to insert at the cursor.
- Bottom right: the mixer (mute and volume per part).
- Toolbar "1小節 _ 拍" (beats per bar): changing it writes `beats:` to the header and re-bars the score text, score view and staff at that many beats (the sound does not change).
- Toolbar "小節の間(ま) _ 拍" (ma between bars): turns the pause between bars on or off and sets its length.
  - **On**: a pause of the given number of beats is inserted at the end of each bar (except the last). During it, every note sounding at the end of the bar (held notes and notes crossing the bar line) is sustained. Parts resting at the end of the bar stay silent.
  - **Off** (unchecked): plays straight through in tempo, as before.
  - The setting is saved as `ma:` in the header. The notation does not change; only the timing of playback and WAV export does.
- Toolbar: play (F5) / play from cursor (F6) / stop (Esc) / speed % / reverb / export WAV.

### Score format (.gaku, UTF-8 text)

```
title: Piece title
mode: 平調          # 壱越調 平調 双調 黄鐘調 盤渉調 太食調
tempo: 60           # BPM per beat
beats: 4            # beats per bar (if omitted, bars follow | in the score)
ma: 1               # length of the pause between bars, in beats; omit or 0 for none

[笙]
乙 - - - | 一 - 工 - |
[竜笛]
干 - 五 丄 | 責干:2 中 夕 |
```

| Token | Meaning |
|---|---|
| `譜字` (a character) | one beat |
| `譜字:2` / `譜字:1/2` | length in beats |
| `-` `ー` | hold the previous note one more beat |
| `-:2` / `-:1/2` | hold the previous note the given number of beats |
| `.` `・` `〇` `休` (also `.:2`) | rest |
| `\|` | bar line (visual only) |
| `tempo=72` | change tempo from this point (applies to all parts) |
| `譜字'` / `譜字,` | one octave up / down |
| `# …` | comment |

A part may be split over several `[instrument]` blocks (they continue one after another). Notes can also follow the instrument name on the same line, as in `[笙] 乙 - 下 |`. If the parts have different lengths, a warning appears in the status bar.

#### Aligning vertically (auto-format)

When you open, save, play or export, or press the "縦にそろえる" (align) button (Ctrl+Shift+F), the score text is formatted like this:

```
# ---- 1〜5小節
[笙]    十    -   凢   -   |  乞  -  一  -  |  ...
[篳篥]  丄    四  六   工  |  五  -  工  六 |  ...
[竜笛]  責丄  干  六   中  |  夕  -  中  六 |  ...
```

- Five bars per system. In each system the lines of all instruments are stacked and the beats line up vertically (in a monospaced font). Bars are separated by `|`.
- Two spaces between beats, one space between notes within a beat (half beats and so on). `乙:2` is rewritten as `乙 -`.
- Formatting never changes the music (start beat, length and tempo changes stay the same). Comments written inside the score body are moved together after the header.
- It does not run while you type; if the columns drift after editing, press Ctrl+Shift+F.

#### Notation per instrument

| Instrument | Characters |
|---|---|
| Shō (笙) | Chords (合竹): 乞 一 工 凢 乙 下 十 美 行 比; special chords 乙美 乙言 凢美 凢言. Prefix 単 (as in `単千`) for a single pipe. In 双調, 十 is the five-note 十. |
| Hichiriki (篳篥) | 舌 五 工 凢 六 四 一 丄 丁 (low to high, G4–A5, standard pitches from Japanese Wikipedia "篳篥"). ム is not used in current pieces. Each note starts with an 塩梅 pitch bend. In 平調, 舌 is lowered from G4 to F#4 and 丄 from G5 to F#5 (メリ). Other modes have no メリ set; override per character in `tunings.json` under `hichiriki`. |
| Ryūteki (竜笛) | 五 丄 夕 中 丅 六 干 (〒) in the low register (和). `責六` or `六'` for the high register (責). 干 sounds above 六 (E6); the low 干 (E5) is `干,`. |
| Gakubiwa (琵琶) | String 1: 一 工 凢 フ 斗 / string 2: 乚 下 十 乙 コ / string 3: ク 七 ヒ 〻 之 / string 4: 丄 八 丨 ム 也 (open, frets 1–4). Normally a sweep (掻撥); `単ク` for a single note. Join with `+`, as in `一+ク`, to strike different strings together (割撥; the same string twice is an error). The sweep "lands" on the beat: the last string (the target note) sounds exactly on the written beat, and the earlier strings are played ahead of it, dividing the preceding beat equally by the number of strings (with 4 strings: 0.75, 0.5 and 0.25 beats early, then on the beat). Change the length with `BIWA_PICKUP_BEATS` in `instruments.py`. |
| Gakusō (筝) | 一–十 斗 為 巾 (single notes); `閑三` = 閑掻, `早三` = 早掻. |
| Kakko (鞨鼓) | 正 (single right stroke), 片来 (roll with the left stick only), 諸来 (roll with both sticks). Give the roll a length, as in `諸来:3`. Rolls start slowly and speed up; the speed follows the tempo (adjust with `KAKKO_ROLL_SPEED` in `instruments.py`). |
| Shōko (鉦鼓) | 金・生 (one stroke), ク (left), レイ (right), クレイ (left then right). |
| Taiko (太鼓) | 図 (light lead-in stroke), 百 (strong stroke). |

### Pitch and tuning

- Reference pitch A4 = 430 Hz (`a4_hz` in `gagaku/tunings.json`), in equal temperament.
- The pitches of the shō pipes and the makeup of its chords, and the pitches of the ryūteki characters, follow the tables in Japanese Wikipedia ("笙", "龍笛").
- **No source was found for the gakubiwa and gakusō tunings in each mode.** They are therefore **provisional**, built from the tonic and scale of each mode. Edit `gagaku/tunings.json` to use accurate tunings (biwa: [open, frets 1–4] per string; koto: the 13 strings 一–巾).
- The 閑掻, 早掻, 掻撥 and 来 techniques are simplified approximations.
- All sounds are synthesized with numpy; no samples are used.
  - Shō: pipes shared between consecutive chords keep sounding, and only the changing pipes enter and leave slightly staggered (手移り). Each chord swells with the breath.
  - Hichiriki and ryūteki: notes up to a rest are synthesized as one phrase and joined with 塩梅 (the hichiriki dips before rising to a higher note). Repeated notes are re-articulated with a short break.
  - Biwa and koto: strings with partials that decay at different rates, plus the sound of the plectrum or picks and the body resonance.
  - Kakko, taiko and shōko: inharmonic membrane and metal modes.
- Write preview WAVs per instrument to `previews/` with `python tools/make_previews.py`.

### Layout

```
main.py                 entry point
gagaku/score.py         score parser
gagaku/instruments.py   notation → pitch/technique, instrument sounds
gagaku/tunings.json     biwa and koto tunings (editable)
gagaku/synth.py         synthesis and reverb
gagaku/render.py        mixing and WAV export
gagaku/audio.py         playback
gagaku/gui.py           Tkinter GUI
gagaku/scoreview.py     score view (five bars per system)
gagaku/formatter.py     score text formatter (aligns beats)
gagaku/staffview.py     staff view (with notation characters)
gagaku/assets/          icon
examples/               sample scores (bundled in the pip package)
tools/make_previews.py  writes preview WAVs per instrument
tools/make_icon.py      rebuilds the icon
tools/make_site_audio.py writes the website's preview MP3s
tests/                  pytest tests
docs/                   website (GitHub Pages)
.github/workflows/      CI (test and build) and PyPI publishing
```

### Development

```bash
pip install -e . pytest
python -m pytest
```

- On every push and pull request, GitHub Actions runs the tests on Windows and Ubuntu with Python 3.10–3.13 and builds the package (`.github/workflows/ci.yml`).
- To publish to PyPI, bump `__version__` in `gagaku/__init__.py`, then create a GitHub release with the matching tag (for example `v0.2.2`); publishing runs automatically (`.github/workflows/publish.yml`, Trusted Publishing).

### License

[MIT License](LICENSE)

---

<a id="japanese"></a>

## 日本語

雅楽の打ち込み・DTM ができる無料のデスクトップアプリ。雅楽の譜字をテキストで入力すると、笙・篳篥・竜笛・琵琶・筝・鞨鼓・鉦鼓・太鼓の合奏として再生する(Windows・macOS・Linux、Python 製)。DAW や音源ソフトは不要で、五線譜表示や WAV 書き出しにも対応する。

紹介サイト(日本語): https://zitengxiang.github.io/gagaku-player/
紹介サイト(英語): https://zitengxiang.github.io/gagaku-player/en/

### インストールと起動

pip で入れる場合:

```bash
pip install gagaku-player
gagaku-player --demo          # サンプル曲「若竹」を開く
gagaku-player 曲.gaku         # 譜面を開く
```

ソースから動かす場合:

```bash
git clone https://github.com/ZiTengXiang/gagaku-player.git
cd gagaku-player
pip install -r requirements.txt
python main.py examples/demo_hyojo.gaku
```

- 必要なもの: Python 3.10+、numpy(tkinter は Python に標準添付)。`python -m gagaku` でも起動できる。
- Windows では追加のインストールは不要(再生に標準の `winsound` を使う)。macOS/Linux では pip で入れると再生用の `sounddevice` も入る(ソースから動かす場合は `pip install sounddevice`)。
- Windows でアイコンから起動したい場合は、`pythonw.exe main.py` を実行するショートカットを作り、アイコンに `gagaku/assets/gagaku.ico` を指定する(`pythonw` ならコンソール画面が出ない)。アイコンは `python tools/make_icon.py` で作り直せる(Pillow と游明朝フォントが必要)。
- コンソールなしで起動して落ちた場合は、`error.log` に詳細を書き出してダイアログを出す。

### 画面

- 左「譜面テキスト」タブ: 譜面エディタ。再生中は鳴っている譜字が黄色くハイライトされる。エラーの行は赤くなる。
- 左「楽譜表示」タブ: 全楽器の拍の頭を縦にそろえ、1段5小節で全楽器を上下に並べた総譜(読み取り専用)。小節の区切りは譜面の `|`、延ばしは細い線で示す。再生中は鳴っている音がハイライトされ、音をクリックするとテキストの該当箇所が選択される(そのまま F6 でそこから再生)。
- 左「五線譜」タブ: 全楽器を1段5小節の総譜として五線譜で書き、各音の下に譜字を付ける(読み取り専用)。1拍 = 4分音符で、小節や拍をまたぐ音はタイでつなぐ。音部記号は楽器の音域から自動で選ぶ(ト音記号・ヘ音記号・オクターブ上下のト音記号)。調号は使わず ♯ を音ごとに付ける。笙は合竹を和音で、琵琶の掻撥と筝の閑掻・早掻は鳴る音をアルペジオ付きの和音で書く。打楽器は1線譜(鞨鼓・鉦鼓は×の符頭、来はトレモロ)。再生ハイライトとクリックでのジャンプは楽譜表示と同じ。
- 右上: 譜字パレット(楽器タブごと)。クリックするとカーソル位置に挿入。
- 右下: ミキサー(パートごとのミュート・音量)。
- ツールバー「1小節 _ 拍」: 1小節の拍数。変えるとヘッダに `beats:` を書き、譜面テキスト・楽譜表示・五線譜を、その拍数ごとの小節に区切り直す(音は変わらない)。
- ツールバー「小節の間(ま) _ 拍」: 小節の間に間(ま)を取るかどうかの切り替えと、その長さ。
  - **間あり**: 各小節の終わり(最後の小節を除く)に指定した拍数の間を挟み、その間は小節の終わりで鳴っている音(延ばしている音・小節線をまたぐ音)をすべて延ばす。小節の終わりで休んでいるパートは休みのまま。
  - **間なし**(チェックを外す): これまでどおりインテンポで続ける。
  - 設定はヘッダの `ma:` に保存される。楽譜の表示は変わらず、再生・WAV書き出しの時間だけが変わる。
- ツールバー: 再生(F5) / カーソル位置から再生(F6) / 停止(Esc) / 速さ% / 残響 / WAV書き出し。

### 譜面の書式(.gaku, UTF-8テキスト)

```
title: 曲名
mode: 平調          # 壱越調 平調 双調 黄鐘調 盤渉調 太食調
tempo: 60           # 1拍あたりのBPM
beats: 4            # 1小節の拍数(省略時は譜面の | で区切る)
ma: 1               # 小節の間(ま)の長さ(拍)。省略または 0 なら間なし

[笙]
乙 - - - | 一 - 工 - |
[竜笛]
干 - 五 丄 | 責干:2 中 夕 |
```

| トークン | 意味 |
|---|---|
| `譜字` | 1拍 |
| `譜字:2` / `譜字:1/2` | 長さ指定(拍) |
| `-` `ー` | 直前の音を1拍延ばす |
| `-:2` / `-:1/2` | 直前の音を指定した拍数だけ延ばす |
| `.` `・` `〇` `休` (`.:2` も可) | 休み |
| `\|` | 小節線(見た目だけ) |
| `tempo=72` | その位置からテンポ変更(全パート共通) |
| `譜字'` / `譜字,` | 1オクターブ上 / 下 |
| `# …` | コメント |

1つのパートを複数の `[楽器]` 段に分けて書いてもよい(後ろへ続く)。`[笙] 乙 - 下 |` のように楽器名と同じ行に音を続けて書くこともできる。パートの長さが揃わないとステータスバーに警告が出る。

#### 縦にそろえる(自動整形)

ファイルを開いたとき・保存したとき・再生/WAV書き出しのとき、または「縦にそろえる」ボタン(Ctrl+Shift+F)で、譜面テキストを次の形に整形する。

```
# ---- 1〜5小節
[笙]    十    -   凢   -   |  乞  -  一  -  |  ...
[篳篥]  丄    四  六   工  |  五  -  工  六 |  ...
[竜笛]  責丄  干  六   中  |  夕  -  中  六 |  ...
```

- 1段に5小節。各段で全楽器の行が上下に並び、拍の頭が縦にそろう(等幅フォント表示で)。小節は `|` で区切る。
- 拍と拍の間は空白2つ、同じ拍の中の音(半拍など)は空白1つ。`乙:2` は `乙 -` のように書き直す。
- 整形しても音は変わらない(各音の開始拍・長さ・テンポ変化は同じ)。本文の途中に書いたコメントはヘッダの後ろへまとめて移る。
- 入力中は自動では動かないので、書き足した後に縦がずれたら Ctrl+Shift+F で直せる。

#### 楽器ごとの譜字

| 楽器 | 譜字 |
|---|---|
| 笙 | 合竹: 乞 一 工 凢 乙 下 十 美 行 比、特殊合竹 乙美 乙言 凢美 凢言。`単千` のように「単」を付けると一本だけ。双調では「十」が5音の十になる。 |
| 篳篥 | 舌 五 工 凢 六 四 一 丄 丁(低い順, G4〜A5、Wikipedia「篳篥」の正律)。ムは現行曲では使わない。音頭に塩梅を付ける。平調では、舌を正律の G4 から F#4(下無)に、丄を G5 から F#5 に半音下げて吹く(メリ)。ほかの調子のメリは未設定で、`tunings.json` の `hichiriki` で譜字ごとに上書きできる。 |
| 竜笛 | 五 丄 夕 中 丅 六 干(〒)(和)。`責六` または `六'` で責。干は六の上(E6)で鳴る。低い干(E5)は `干,`。 |
| 琵琶 | 1弦 一 工 凢 フ 斗 / 2弦 乚 下 十 乙 コ / 3弦 ク 七 ヒ 〻 之 / 4弦 丄 八 丨 ム 也(開放, 第1〜4柱)。通常は掻撥、`単ク` で単音。`一+ク` のように `+` でつなぐと、別々の弦を同時に鳴らす(割撥。同じ弦どうしはエラー)。掻撥は「着地型」で、最後の弦(目的の音)を譜面の位置の拍頭ちょうどに鳴らし、それより前の弦は直前の1拍を弦の数で等分して先に弾く(4本なら 0.75・0.5・0.25 拍前と拍頭。`instruments.py` の `BIWA_PICKUP_BEATS` で長さを変更可)。 |
| 筝 | 一〜十 斗 為 巾(単音)、`閑三` = 閑掻、`早三` = 早掻。 |
| 鞨鼓 | 正(右の単打)、片来(左桴のみのロール)、諸来(両桴のロール)。ロールは `諸来:3` のように長さを指定。来は打ち始めが間遠く次第に速まり、速さはテンポに連動する(`instruments.py` の `KAKKO_ROLL_SPEED` で調整可)。 |
| 鉦鼓 | 金・生(一打)、ク(左)、レイ(右)、クレイ(左右2打)。 |
| 太鼓 | 図(軽い前打)、百(強打)。 |

### 音高・調弦について

- 基準ピッチは A4 = 430 Hz(`gagaku/tunings.json` の `a4_hz`)。平均律で計算している。
- 笙の各竹の音高と合竹の構成、竜笛の譜字の音高は、Wikipedia「笙」「龍笛」の表による。
- **楽琵琶・楽箏の調子ごとの調弦は、調べた範囲では出典が見つからなかった。** そのため各調子の主音と音階から組んだ**暫定値**になっている。正確な調弦は `gagaku/tunings.json` を書き換えれば反映される(琵琶は各弦の[開放, 第1〜4柱]、筝は一〜巾の13弦)。
- 閑掻・早掻・掻撥・来の奏法は、手順を簡略化した近似。
- 音色は numpy による合成で、サンプル音源ではない。
  - 笙: 合竹が替わっても共通の竹は鳴り続け、入れ替わる竹だけが手移りで少しずつずれて出入りする。合竹ごとに息で膨らむ。
  - 篳篥・竜笛: 休みまでの音をひと続きのフレーズとして合成し、音と音の間を塩梅でつなぐ(篳篥は上行時にいったん下げてから押し上げる)。同じ音が続くときは指打ちで切る。
  - 琵琶・筝: 倍音ごとに減衰の違う弦の音に、撥・爪の打撃音と胴の共鳴を加える。
  - 鞨鼓・太鼓・鉦鼓: 膜・金属の非整数倍モードによる合成。
- 楽器ごとの試聴用WAVは `python tools/make_previews.py` で `previews/` に書き出せる。

### 構成

```
main.py                 起動
gagaku/score.py         譜面パーサ
gagaku/instruments.py   譜字→音高/奏法、楽器ごとの音色
gagaku/tunings.json     琵琶・筝の調弦(編集可)
gagaku/synth.py         合成・残響
gagaku/render.py        ミックス・WAV書き出し
gagaku/audio.py         再生
gagaku/gui.py           Tkinter GUI
gagaku/scoreview.py     楽譜表示(1段5小節の総譜)
gagaku/formatter.py     譜面テキストの整形(拍頭を縦にそろえる)
gagaku/staffview.py     五線譜表示(字譜つき)
gagaku/assets/          アイコン
examples/               サンプル譜(pip 版ではパッケージ内に同梱)
tools/make_previews.py  楽器ごとの試聴用WAVを書き出す
tools/make_icon.py      アイコンを作り直す
tools/make_site_audio.py 紹介サイトの試聴用MP3を書き出す
tests/                  pytest のテスト
docs/                   紹介サイト(GitHub Pages)
.github/workflows/      CI(テスト・ビルド)と PyPI への公開
```

### 開発

```bash
pip install -e . pytest
python -m pytest
```

- push や pull request のたびに、GitHub Actions が Windows / Ubuntu × Python 3.10〜3.13 でテストし、パッケージをビルドする(`.github/workflows/ci.yml`)。
- PyPI への公開は、`gagaku/__init__.py` の `__version__` を上げてから、同じ番号のタグ(例 `v0.2.2`)で GitHub のリリースを作ると自動で行われる(`.github/workflows/publish.yml`、Trusted Publishing)。

### ライセンス

[MIT License](LICENSE)
