from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import ValidationError
from sqlalchemy import literal, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import Session

from backend.app.api.deps import get_current_admin, get_current_employee
from backend.app.core.database import get_db
from backend.app.models.employee import Employee
from backend.app.models.workbench_tile import UserHiddenPresetTile, WorkbenchTile
from backend.app.schemas.workbench_tile import TileList, TileRead, TileReorder, TileUpdate, TileWrite

router = APIRouter(prefix="/workbench", tags=["工作台磁贴"])
admin_router = APIRouter(
    prefix="/admin/workbench", tags=["工作台磁贴管理"], dependencies=[Depends(get_current_admin)]
)


def find_tile(db: Session, tile_id: int, owner: str | None) -> WorkbenchTile:
    tile = db.query(WorkbenchTile).filter_by(id=tile_id, owner_emp_no=owner).first()
    if tile is None:
        raise HTTPException(404, "磁贴不存在")
    return tile


def create_tile(db: Session, owner: str | None, payload: TileWrite) -> WorkbenchTile:
    tile = WorkbenchTile(owner_emp_no=owner, **payload.model_dump())
    db.add(tile)
    db.commit()
    db.refresh(tile)
    return tile


def update_tile(db: Session, tile: WorkbenchTile, payload: TileUpdate) -> WorkbenchTile:
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return tile
    values = {field: getattr(tile, field) for field in TileWrite.model_fields}
    values.update(changes)
    try:
        validated = TileWrite.model_validate(values)
    except ValidationError as exc:
        raise HTTPException(422, "磁贴内容无效，请检查必填项与链接格式") from exc
    values = validated.model_dump(include=set(changes))
    query = db.query(WorkbenchTile).filter_by(id=tile.id, owner_emp_no=tile.owner_emp_no)
    if changes.keys() & {"tile_type", "payload"}:
        # A concurrent update could otherwise invalidate the pair we just validated.
        query = query.filter_by(tile_type=tile.tile_type, payload=tile.payload)
    if not query.update(values, synchronize_session=False):
        raise HTTPException(409, "磁贴已变更，请刷新后重试")
    db.commit()
    db.refresh(tile)
    return tile


@router.get("/tiles", response_model=TileList)
def list_tiles(
    employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)
):
    hidden_ids = db.query(UserHiddenPresetTile.tile_id).filter_by(emp_no=employee.emp_no)
    visible = db.query(WorkbenchTile).filter(
        or_(
            WorkbenchTile.owner_emp_no == employee.emp_no,
            WorkbenchTile.owner_emp_no.is_(None)
            & WorkbenchTile.is_enabled.is_(True)
            & WorkbenchTile.id.not_in(hidden_ids.statement),
        )
    )
    hidden = db.query(WorkbenchTile).filter(
        WorkbenchTile.owner_emp_no.is_(None), WorkbenchTile.id.in_(hidden_ids.statement)
    )
    order = (WorkbenchTile.sort_order, WorkbenchTile.id)
    return {"tiles": visible.order_by(*order).all(), "hidden_presets": hidden.order_by(*order).all()}


@router.post("/tiles", response_model=TileRead, status_code=201)
def add_personal_tile(
    payload: TileWrite,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return create_tile(db, employee.emp_no, payload)


@router.post("/tiles/reorder", status_code=204)
def reorder_tiles(
    payload: TileReorder,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    orders = {item.id: item.sort_order for item in payload.items}
    tiles = db.query(WorkbenchTile).filter(
        WorkbenchTile.owner_emp_no == employee.emp_no, WorkbenchTile.id.in_(orders)
    ).all()
    if len(tiles) != len(orders):
        raise HTTPException(404, "部分个人磁贴不存在")
    for tile in tiles:
        tile.sort_order = orders[tile.id]
    db.commit()
    return Response(status_code=204)


@router.patch("/tiles/{tile_id}", response_model=TileRead)
def edit_personal_tile(
    tile_id: int,
    payload: TileUpdate,
    employee: Employee = Depends(get_current_employee),
    db: Session = Depends(get_db),
):
    return update_tile(db, find_tile(db, tile_id, employee.emp_no), payload)


@router.delete("/tiles/{tile_id}", status_code=204)
def delete_personal_tile(
    tile_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)
):
    db.delete(find_tile(db, tile_id, employee.emp_no))
    db.commit()
    return Response(status_code=204)


@router.post("/presets/{tile_id}/hide", status_code=204)
def hide_preset(
    tile_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)
):
    preset = select(literal(employee.emp_no), WorkbenchTile.id).where(
        WorkbenchTile.id == tile_id, WorkbenchTile.owner_emp_no.is_(None)
    )
    result = db.execute(
        insert(UserHiddenPresetTile)
        .from_select(["emp_no", "tile_id"], preset)
        .on_conflict_do_nothing(index_elements=["emp_no", "tile_id"])
    )
    if not result.rowcount:
        find_tile(db, tile_id, None)
    db.commit()
    return Response(status_code=204)


@router.delete("/presets/{tile_id}/hide", status_code=204)
def restore_preset(
    tile_id: int, employee: Employee = Depends(get_current_employee), db: Session = Depends(get_db)
):
    find_tile(db, tile_id, None)
    db.query(UserHiddenPresetTile).filter_by(emp_no=employee.emp_no, tile_id=tile_id).delete()
    db.commit()
    return Response(status_code=204)


@admin_router.get("/presets", response_model=list[TileRead])
def list_presets(db: Session = Depends(get_db)):
    return db.query(WorkbenchTile).filter_by(owner_emp_no=None).order_by(
        WorkbenchTile.sort_order, WorkbenchTile.id
    ).all()


@admin_router.post("/presets", response_model=TileRead, status_code=201)
def add_preset(payload: TileWrite, db: Session = Depends(get_db)):
    return create_tile(db, None, payload)


@admin_router.patch("/presets/{tile_id}", response_model=TileRead)
def edit_preset(tile_id: int, payload: TileUpdate, db: Session = Depends(get_db)):
    return update_tile(db, find_tile(db, tile_id, None), payload)


@admin_router.delete("/presets/{tile_id}", status_code=204)
def delete_preset(tile_id: int, db: Session = Depends(get_db)):
    tile = find_tile(db, tile_id, None)
    db.query(UserHiddenPresetTile).filter_by(tile_id=tile_id).delete()
    db.delete(tile)
    db.commit()
    return Response(status_code=204)
