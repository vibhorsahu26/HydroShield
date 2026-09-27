from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session
from shapely import from_wkb
from shapely.geometry import box

from app.database.models import SpatialFeature, new_id


class SpatialFeatureRepository:
    def create(
        self,
        db: Session,
        *,
        project_id: str,
        dataset_id: str | None,
        feature_type: str,
        geometry_wkb: bytes,
        geometry_srid: int,
        properties: dict,
    ) -> SpatialFeature:
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            result = db.execute(
                text(
                    """
                    INSERT INTO spatial_features
                        (id, project_id, dataset_id, feature_type, geom, geometry_srid, properties, created_at)
                    VALUES
                        (:id, :project_id, :dataset_id, :feature_type,
                         ST_SetSRID(ST_GeomFromWKB(:geom_wkb), :srid),
                         :srid, :properties, NOW())
                    RETURNING id, project_id, dataset_id, feature_type,
                              ST_AsBinary(geom) AS geom, geometry_srid, properties, created_at
                    """
                ),
                {
                    "id": new_id(),
                    "project_id": project_id,
                    "dataset_id": dataset_id,
                    "feature_type": feature_type,
                    "geom_wkb": geometry_wkb,
                    "srid": geometry_srid,
                    "properties": properties,
                },
            ).mappings().one()
            feature = SpatialFeature(**dict(result))
            db.commit()
            return feature

        feature = SpatialFeature(
            project_id=project_id,
            dataset_id=dataset_id,
            feature_type=feature_type,
            geom=geometry_wkb,
            geometry_srid=geometry_srid,
            properties=properties,
        )
        db.add(feature)
        db.commit()
        db.refresh(feature)
        return feature

    def intersects_bbox(
        self,
        db: Session,
        *,
        project_id: str,
        bbox: tuple[float, float, float, float],
        srid: int,
    ) -> list[SpatialFeature | dict]:
        minx, miny, maxx, maxy = bbox
        if db.bind is not None and db.bind.dialect.name == "postgresql":
            rows = db.execute(
                text(
                    """
                    SELECT id, project_id, dataset_id, feature_type,
                           ST_AsBinary(geom) AS geom, geometry_srid, properties, created_at
                    FROM spatial_features
                    WHERE project_id = :project_id
                      AND ST_Intersects(
                            geom,
                            ST_MakeEnvelope(:minx, :miny, :maxx, :maxy, :srid)
                      )
                    ORDER BY created_at DESC
                    """
                ),
                {
                    "project_id": project_id,
                    "minx": minx,
                    "miny": miny,
                    "maxx": maxx,
                    "maxy": maxy,
                    "srid": srid,
                },
            ).mappings().all()
            return [dict(row) for row in rows]

        target = box(minx, miny, maxx, maxy)
        rows = db.query(SpatialFeature).filter(SpatialFeature.project_id == project_id).all()
        return [row for row in rows if from_wkb(row.geom).intersects(target)]
