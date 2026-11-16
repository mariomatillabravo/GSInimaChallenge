import styles from "./App.module.css";
import { DemoBanner } from "./components/DemoBanner";
import { Footer } from "./components/Footer";

export function App() {
  return (
    <div className={styles.layout}>
      <header className={styles.header}>
        <h1 className={styles.title}>AEMET Antarctica Weather</h1>
        <p className={styles.subtitle}>Weather measurements from the Spanish Antarctic stations</p>
      </header>
      <main className={styles.main}>
        <DemoBanner />
      </main>
      <Footer />
    </div>
  );
}
