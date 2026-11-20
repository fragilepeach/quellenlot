"use strict";

const parliamentaryCases = [
  {
    id: "schuldenbremse-2025",
    title: "Schuldenbremse und Investitionen",
    scope: "Bundestagswahl 2025 · Haushalt",
    featuredRecord: "schuldenbremse-schluss",
    proposition: "Der Bund soll die Kreditregeln ändern, um zusätzliche öffentliche Investitionen zu ermöglichen.",
    context: {
      text: "Die Bundestagswahl war am 23. Februar 2025. Über die Grundgesetzänderung stimmte am 18. März noch der 20. Bundestag ab, vor dem Zusammentritt des neu gewählten Parlaments. Die Zahlen geben das Stimmverhalten der damaligen Fraktionen wieder.",
      source: {
        label: "Bundestag · Bericht zur Sondersitzung",
        url: "https://www.bundestag.de/dokumente/textarchiv/2025/kw12-de-sondersitzung-1056916",
      },
    },
    programmes: [
      {
        party: "CDU/CSU",
        date: "2024-12-17",
        quote: "An der grundgesetzlichen Schuldenbremse festhalten.",
        source: {
          label: "Wahlprogramm · S. 75",
          url: "https://www.csu.de/common/fu/content/PDFs/Pressemitteilungen/Wahlprogramm_2025_von_CDU_und_CSU.pdf#page=75",
        },
        position: "open",
        assessment: "Spannung zur Ankündigung",
        explanation: "Die Fraktion trug neue Ausnahmen und Kreditspielräume mit. Die Schuldenregel blieb mit geänderten Grenzen im Grundgesetz verankert. Ob darin ein Widerspruch liegt, hängt davon ab, ob „festhalten“ den Fortbestand der Regel oder ihre bisherige Reichweite meint.",
        records: ["schuldenbremse-schluss", "schuldenbremse-gesetz"],
      },
      {
        party: "SPD",
        date: "2025-01-11",
        quote: "Deshalb wollen wir die Schuldenregel im Grundgesetz so reformieren, dass Investitionen in die Zukunftsfähigkeit unseres Landes und in den Wohlstand nicht behindert werden.",
        source: {
          label: "Wahlprogramm · II. Ein neuer Aufschwung für Deutschland",
          url: "https://www.spd.de/bundestagswahl/programm/uebersicht/ii-ein-neuer-aufschwung-fuer-deutschland",
        },
        position: "agree",
        assessment: "Entspricht der angekündigten Richtung",
        explanation: "Die Fraktion brachte den Entwurf mit ein und stimmte mehrheitlich für die Ausschussfassung. Die Verfassungsänderung und das spätere Errichtungsgesetz schufen den Kreditrahmen für zusätzliche Investitionen. Umfang und Wirkung der tatsächlichen Ausgaben bleiben gesondert zu prüfen.",
        records: ["schuldenbremse-schluss", "schuldenbremse-svikg"],
      },
    ],
    records: [
      {
        id: "schuldenbremse-entwurf",
        date: "2025-03-10",
        type: "Gesetzentwurf",
        title: "SPD und CDU/CSU bringen die Grundgesetzänderung ein",
        text: "Der Entwurf 20/15096 verbindet Änderungen an den Kreditregeln mit einer Ermächtigung für ein Infrastruktur-Sondervermögen. Der Haushaltsausschuss empfiehlt am 16. März eine geänderte Fassung, die auch Investitionen zur Klimaneutralität ausdrücklich erfasst.",
        sources: [
          { label: "Entwurf · 20/15096", url: "https://dserver.bundestag.de/btd/20/150/2015096.pdf" },
          { label: "Ausschussfassung · 20/15117", url: "https://dserver.bundestag.de/btd/20/151/2015117.pdf#page=10" },
        ],
      },
      {
        id: "schuldenbremse-aenderung",
        date: "2025-03-18",
        type: "Namentliche Abstimmung · Änderungsantrag",
        title: "FDP-Änderungsantrag zum Verteidigungsfonds",
        shortTitle: "Änderungsantrag",
        text: "Die FDP beantragte in der zweiten Beratung, den Artikel 1 des Entwurfs durch eine Regelung zu einem Verteidigungsfonds zu ersetzen. Die Abstimmung galt dieser Änderung des Entwurfs.",
        quote: "als Sondervermögen für die Bundeswehr mit eigener Kreditermächtigung in Höhe von einmalig bis zu 300 Milliarden Euro",
        result: "Abgelehnt",
        tally: [
          { group: "Gesamt", counts: [85, 630, 2, 16] },
          { group: "CDU/CSU", counts: [0, 193, 1, 2] },
          { group: "SPD", counts: [0, 205, 0, 2] },
          { group: "FDP", counts: [85, 1, 1, 3] },
        ],
        sources: [
          { label: "Wortlaut · 20/15120, S. 1", url: "https://dserver.bundestag.de/btd/20/151/2015120.pdf#page=1" },
          { label: "Namentliche Stimmen · Nr. 950", url: "https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=950" },
          { label: "Plenarprotokoll · 20/214", url: "https://dserver.bundestag.de/btp/20/20214.pdf" },
        ],
      },
      {
        id: "schuldenbremse-schluss",
        date: "2025-03-18",
        type: "Namentliche Abstimmung · Schlussabstimmung",
        title: "Grundgesetzänderung in der Ausschussfassung",
        shortTitle: "Schlussabstimmung",
        text: "Zur Abstimmung stand der Entwurf 20/15096 in der Fassung des Haushaltsausschusses (20/15117, Buchstabe a). Das Paket enthielt Kreditspielräume für die Länder, Ausnahmen für Sicherheitsausgaben oberhalb von einem Prozent des BIP und ein Sondervermögen von bis zu 500 Milliarden Euro für Infrastruktur und Klimaneutralität.",
        quote: "Auf die Kreditermächtigung sind Artikel 109 Absatz 3 und Artikel 115 Absatz 2 nicht anzuwenden.",
        context: "Der Ausschnitt stammt aus dem vorgeschlagenen Art. 143h Abs. 1. Die Stimmen gelten dem gesamten Paket. Die Haltung zu einzelnen Bestandteilen bleibt aus dem Abstimmungsergebnis offen.",
        result: "Mit Zweidrittelmehrheit angenommen",
        tally: [
          { group: "Gesamt", counts: [512, 206, 0, 15] },
          { group: "CDU/CSU", counts: [193, 1, 0, 2] },
          { group: "SPD", counts: [205, 1, 0, 1] },
          { group: "FDP", counts: [0, 87, 0, 3] },
        ],
        sources: [
          { label: "Wortlaut · 20/15117, S. 10", url: "https://dserver.bundestag.de/btd/20/151/2015117.pdf#page=10" },
          { label: "Namentliche Stimmen · Nr. 951", url: "https://www.bundestag.de/parlament/plenum/abstimmung/abstimmung?id=951" },
          { label: "Plenarprotokoll · 20/214", url: "https://dserver.bundestag.de/btp/20/20214.pdf" },
        ],
      },
      {
        id: "schuldenbremse-gesetz",
        date: "2025-03-24",
        type: "Verkündung",
        title: "Grundgesetzänderung im Bundesgesetzblatt",
        shortTitle: "Verkündung",
        text: "Das Gesetz vom 22. März wird nach Zustimmung des Bundesrates verkündet und tritt am 25. März in Kraft. Es ändert Art. 109 und 115 und fügt Art. 143h hinzu.",
        sources: [
          { label: "BGBl. 2025 I Nr. 94 · Art. 1 und 2", url: "https://www.recht.bund.de/bgbl/1/2025/94/regelungstext.pdf?__blob=publicationFile&v=3" },
        ],
      },
      {
        id: "schuldenbremse-svikg",
        date: "2025-09-18",
        type: "Spätere Umsetzung",
        title: "Bundestag beschließt das Errichtungsgesetz",
        shortTitle: "Spätere Umsetzung",
        text: "Der 21. Bundestag beschließt den Entwurf von CDU/CSU und SPD zur Errichtung des Sondervermögens. Das Gesetz vom 30. September konkretisiert Zweck und Mittelverwendung. Die Höhe bezeichnet einen Finanzierungsrahmen.",
        sources: [
          { label: "Gesetzesbeschluss · BR-Drs. 494/25", url: "https://dserver.bundestag.de/brd/2025/0494-25.pdf" },
          { label: "SVIKG · §§ 1–2", url: "https://www.gesetze-im-internet.de/svikg/BJNR0E60A0025.html" },
        ],
      },
    ],
  },
];
