# SBBN Toolbox — règles de contribution

- Respecter l'architecture `ui -> viewmodels -> services`.
- Ne jamais mettre de manipulation PDF directement dans les widgets.
- Ne jamais modifier un fichier source utilisateur.
- Ne jamais conserver un document traité dans `data`, le dossier du programme ou `%TEMP%`.
- Toute écriture de résultat doit être atomique et nettoyée dans un bloc `finally`.
- Ne jamais utiliser de suppression récursive sur un chemin non résolu et non validé.
- Limiter le nettoyage aux fichiers ou dossiers créés par l'opération courante.
- Tout traitement de plusieurs pages doit être annulable et exécuté hors du thread UI.
- Ajouter ou adapter les tests avec chaque modification métier.
- Exécuter Ruff et pytest avant de déclarer une phase terminée.
- Conserver les textes d'interface en français dans un module centralisé.
- Utiliser uniquement les tokens du design system SBBN pour les couleurs et espacements.
- Ne pas ajouter de télémétrie. Limiter l'accès réseau au service de mise à jour public,
  sans token GitHub ni envoi de données personnelles.
- Ne pas élargir le périmètre d'une phase sans demande explicite.
