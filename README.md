# V-P2000

Snelle P2000-alarmering in Home Assistant. Licht aan, omroep op je speakers, of wat je maar wilt, zodra jouw capcodes worden opgeroepen.

> **Let op:** V-P2000 is een extraatje naast je pieper, geen vervanging. Het werkt via internet en een gratis dienst van derden. Vertrouw voor je alarmering altijd op je pieper.

## Wat het doet

- Haalt meldingen op bij [AlarmeringDroid](https://beta.alarmeringdroid.nl), standaard elke 10 seconden. Alle capcodes gaan in **één** request.
- Bij elke **nieuwe oproep** op een van jouw capcodes vuurt V-P2000 direct het event `v_p2000_alarm` af. Dat geldt ook voor een bijalarmering in een melding die al liep. Je automations triggeren op dat event, dus er zit geen extra vertraging in.
- Na een herstart van Home Assistant roept het alleen meldingen om die hooguit 5 minuten oud zijn. Oude meldingen krijg je dus niet opnieuw te horen.

Gemeten: AlarmeringDroid heeft een oproep meestal binnen enkele seconden. Met een interval van 10 s zit je dan meestal **5 tot 15 seconden** na je pieper.

## Installeren

**Via HACS (aanbevolen):** HACS → ⋮ → *Aangepaste repositories* → voeg de URL van deze repository toe als type *Integratie*. Zoek daarna op **V-P2000** en installeer.

**Handmatig:** kopieer de map `custom_components/v_p2000` naar `config/custom_components/` van je Home Assistant.

Herstart daarna Home Assistant.

## Instellen

*Instellingen → Apparaten & diensten → Integratie toevoegen → V-P2000*

Vul één groep per regel in, als `naam: capcode, capcode`:

```
's Gravenmoer: 1200268, 1201507, 1201940
TDV: 1201600, 1201224
```

Groepen en interval pas je later aan via **Configureren**.

**Interval:** AlarmeringDroid is een gratis dienst. Gebruik daarom de standaard 10 seconden; 5 seconden kan als elke seconde telt. V-P2000 doet zelf ook rustig aan:
- Kost een vraag de server veel tijd, dan wacht V-P2000 daarna minstens 2× zo lang.
- Bij storingen wacht het steeds langer tussen pogingen (tot 15 s).
- Het maakt zich bekend met de User-Agent `V-P2000/<versie>`.

## Entiteiten

| Entiteit | Wat |
|---|---|
| `sensor.v_p2000_<groep>` | Tijdstip van het laatste alarm van die groep. De details staan in de attributen. |
| `binary_sensor.v_p2000_verbinding` | Gaat **uit** als AlarmeringDroid een minuut niet bereikbaar is; dan komen er geen alarmen door. Handig om een melding op te zetten. |

## Event `v_p2000_alarm`

| Veld | Voorbeeld |
|---|---|
| `groep` / `groep_naam` | `s_gravenmoer` / `'s Gravenmoer` |
| `groepen` | alle groepen die in deze oproep zitten |
| `melding` | `P 1 BZB-01 BR container Luiten Ambachtstraat Raamsdonk 207332` |
| `tekstmelding` | leesbare tekst van AlarmeringDroid, als die er is |
| `capcodes` | jouw capcodes in deze oproep |
| `plaats`, `straat`, `dienst`, `regio`, `datum`, `tijd`, `prio1` | |
| `latitude`, `longitude` | |
| `id`, `groep_id` | id van de oproep en van de melding waar hij bij hoort |
| `bron` | `alarmeringdroid`, of `test` |

**Testen:** *Ontwikkelaarshulpmiddelen → Acties → V-P2000: Testalarm* vuurt een test-event af, met `bron: test`.

## Voorbeeld-automation

Licht aan, omroep op Sonos-speakers, en na 2 uur licht weer uit:

```yaml
# configuration.yaml
timer:
  p2000_licht_uit:
    duration: "02:00:00"
    restore: true
```

```yaml
- alias: P2000 omroep
  triggers:
    - trigger: event
      event_type: v_p2000_alarm
  actions:
    - parallel:
        - action: light.turn_on
          target: { area_id: woonkamer }
          continue_on_error: true
        - action: timer.start
          target: { entity_id: timer.p2000_licht_uit }
        - action: media_player.play_media
          continue_on_error: true
          target:
            entity_id: [media_player.woonkamer, media_player.slaapkamer]
          data:
            media_content_id: >-
              media-source://tts/tts.google_translate_nl_com?message={{ trigger.event.data.melding | urlencode }}&language=nl
            media_content_type: music
            announce: true
            extra:
              volume: 50   # Sonos: 0-100, NIET 0.5
    - delay: { seconds: 20 }   # ruimte voor een tweede oproep vlak erna
  mode: queued

- alias: P2000 licht uit na 2 uur
  triggers:
    - trigger: event
      event_type: timer.finished
      event_data: { entity_id: timer.p2000_licht_uit }
  actions:
    - action: light.turn_off
      target: { area_id: woonkamer }
```

Tips:
- Met `announce: true` kun je pauzeren en het volume terugzetten weglaten: een Sonos zet de muziek na de omroep zelf weer voort.
- Gebruik je eigen TTS-entiteit. Je vindt hem onder *Ontwikkelaarshulpmiddelen → Statussen*, filter op `tts.`.
- `mode: queued` zorgt dat een tweede oproep, bijvoorbeeld een bijalarmering, niet verloren gaat.

## Bijdragen en credits

- Meldingen: [AlarmeringDroid](https://beta.alarmeringdroid.nl).
- Geïnspireerd op [ha_p2000](https://github.com/dutch-erik/ha_p2000).
- De logica testen zonder Home Assistant: `python3 tests/test_logic.py`.

Licentie: MIT, zie [LICENSE](LICENSE).
