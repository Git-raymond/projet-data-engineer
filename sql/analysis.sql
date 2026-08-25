-- 1. Chiffre d'affaires total
SELECT ROUND(SUM(s.quantity * p.price), 2) AS chiffre_affaires_total
FROM sales s JOIN products p ON p.product_ref = s.product_ref;

-- 2. Ventes par produit
SELECT p.product_ref, p.name,
       SUM(s.quantity) AS quantite_vendue,
       ROUND(SUM(s.quantity * p.price), 2) AS chiffre_affaires
FROM sales s JOIN products p ON p.product_ref = s.product_ref
GROUP BY p.product_ref, p.name
ORDER BY chiffre_affaires DESC;

-- 3. Ventes par région / ville
SELECT st.city AS region,
       SUM(s.quantity) AS quantite_vendue,
       ROUND(SUM(s.quantity * p.price), 2) AS chiffre_affaires
FROM sales s
JOIN products p ON p.product_ref = s.product_ref
JOIN stores st ON st.store_id = s.store_id
GROUP BY st.city
ORDER BY chiffre_affaires DESC;

-- 4. Résultats stockés
SELECT * FROM analysis_results
ORDER BY analysis_type, metric_revenue DESC;
