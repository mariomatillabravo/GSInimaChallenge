import styles from "./Footer.module.css";

export const AEMET_OPENDATA_URL = "https://opendata.aemet.es/centrodedescargas/inicio";
export const AEMET_LEGAL_NOTICE_URL = "https://www.aemet.es/es/nota_legal";

/** AEMET's terms of use allow reusing its data provided AEMET is cited as the author. */
export function Footer() {
  return (
    <footer className={styles.footer}>
      <p className={styles.text}>
        Data: <a href={AEMET_OPENDATA_URL}>AEMET OpenData</a>. © AEMET. Use and reproduction of the
        information is authorised provided AEMET is cited as its author (
        <a href={AEMET_LEGAL_NOTICE_URL}>legal notice</a>).
      </p>
    </footer>
  );
}
