from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional, TypeVar, Union

from typing_extensions import Self

from dagster import Field
from dagster import _check as check
from dagster._config import EvaluateValueResult

from .definition_config_schema import (
    CoercableToConfigSchema,
    ConfiguredDefinitionConfigSchema,
    IDefinitionConfigSchema,
    convert_user_facing_definition_config_schema,
)


class ConfigurableDefinition(ABC):
    @property
    @abstractmethod
    def config_schema(self) -> Optional[IDefinitionConfigSchema]:
        raise NotImplementedError()

    @property
    def has_config_field(self) -> bool:
        return self.config_schema is not None and bool(self.config_schema.as_field())

    @property
    def config_field(self) -> Optional[Field]:
        return None if not self.config_schema else self.config_schema.as_field()

    # getter for typed access
    def get_config_field(self) -> Field:
        field = self.config_field
        if field is None:
            check.failed("Must check has_config_Field before calling get_config_field")
        return field

    def apply_config_mapping(self, config: Any) -> EvaluateValueResult:
        """
        Applies user-provided config mapping functions to the given configuration and validates the
        results against the respective config schema.

        Expects incoming config to be validated and have fully-resolved values (StringSource values
        resolved, Enum types hydrated, etc.) via process_config() during ResolvedRunConfig
        construction and CompositeSolid config mapping.

        Args:
            config (Any): A validated and resolved configuration dictionary matching this object's
            config_schema

        Returns (EvaluateValueResult):
            If successful, the value is a validated and resolved configuration dictionary for the
            innermost wrapped object after applying the config mapping transformation function.
        """
        # If schema is on a mapped schema this is the innermost resource (base case),
        # so we aren't responsible for validating against anything farther down.
        # Returns an EVR for type consistency with config_mapping_fn.
        return (
            self.config_schema.resolve_config(config)
            if isinstance(self.config_schema, ConfiguredDefinitionConfigSchema)
            else EvaluateValueResult.for_value(config)
        )


class AnonymousConfigurableDefinition(ConfigurableDefinition):
    """An interface that makes the `configured` method not accept a name argument."""

    def configured(
        self,
        config_or_config_fn: Any,
        config_schema: CoercableToConfigSchema = None,
        description: Optional[str] = None,
    ) -> Self:  # type: ignore [valid-type] # (until mypy supports Self)
        """
        Wraps this object in an object of the same type that provides configuration to the inner
        object.

        Using ``configured`` may result in config values being displayed in
        Dagit, so it is not recommended to use this API with sensitive values,
        such as secrets.

        Args:
            config_or_config_fn (Union[Any, Callable[[Any], Any]]): Either (1) Run configuration
                that fully satisfies this object's config schema or (2) A function that accepts run
                configuration and returns run configuration that fully satisfies this object's
                config schema.  In the latter case, config_schema must be specified.  When
                passing a function, it's easiest to use :py:func:`configured`.
            config_schema (ConfigSchema): If config_or_config_fn is a function, the config schema
                that its input must satisfy.
            description (Optional[str]): Description of the new definition. If not specified,
                inherits the description of the definition being configured.

        Returns (ConfigurableDefinition): A configured version of this object.
        """

        new_config_schema = ConfiguredDefinitionConfigSchema(
            self, convert_user_facing_definition_config_schema(config_schema), config_or_config_fn
        )

        return self.copy_for_configured(description, new_config_schema, config_or_config_fn)

    @abstractmethod
    def copy_for_configured(
        self,
        description: Optional[str],
        config_schema: IDefinitionConfigSchema,
        config_or_config_fn: Union[Any, Callable[[Any], Any]],
    ) -> Self:  # type: ignore [valid-type] # (until mypy supports Self)
        raise NotImplementedError()


class NamedConfigurableDefinition(ConfigurableDefinition):
    """An interface that makes the `configured` method require a positional `name` argument."""

    def configured(
        self,
        config_or_config_fn: Any,
        name: str,
        config_schema: Optional[Dict[str, Any]] = None,
        description: Optional[str] = None,
    ) -> Self:  # type: ignore [valid-type] # (until mypy supports Self)
        """
        Wraps this object in an object of the same type that provides configuration to the inner
        object.

        Using ``configured`` may result in config values being displayed in
        Dagit, so it is not recommended to use this API with sensitive values,
        such as secrets.

        Args:
            config_or_config_fn (Union[Any, Callable[[Any], Any]]): Either (1) Run configuration
                that fully satisfies this object's config schema or (2) A function that accepts run
                configuration and returns run configuration that fully satisfies this object's
                config schema.  In the latter case, config_schema must be specified.  When
                passing a function, it's easiest to use :py:func:`configured`.
            name (str): Name of the new definition. This is a required argument, as this definition
                type has a name uniqueness constraint.
            config_schema (ConfigSchema): If config_or_config_fn is a function, the config schema
                that its input must satisfy.
            description (Optional[str]): Description of the new definition. If not specified,
                inherits the description of the definition being configured.

        Returns (ConfigurableDefinition): A configured version of this object.
        """

        name = check.str_param(name, "name")

        new_config_schema = ConfiguredDefinitionConfigSchema(
            self, convert_user_facing_definition_config_schema(config_schema), config_or_config_fn
        )

        return self.copy_for_configured(name, description, new_config_schema, config_or_config_fn)

    @abstractmethod
    def copy_for_configured(
        self,
        name: str,
        description: Optional[str],
        config_schema: IDefinitionConfigSchema,
        config_or_config_fn: Union[Any, Callable[[Any], Any]],
    ) -> Self:  # type: ignore [valid-type] # (until mypy supports Self)
        ...


def _check_configurable_param(configurable: ConfigurableDefinition) -> None:
    from dagster._core.definitions.composition import PendingNodeInvocation

    check.param_invariant(
        not isinstance(configurable, PendingNodeInvocation),
        "configurable",
        (
            "You have invoked `configured` on a PendingNodeInvocation (an intermediate type), which is "
            "produced by aliasing or tagging a solid definition. To configure a solid, you must "
            "call `configured` on either a SolidDefinition and CompositeSolidDefinition. To fix "
            "this error, make sure to call `configured` on the definition object *before* using "
            "the `tag` or `alias` methods. For usage examples, see "
            "https://docs.dagster.io/concepts/configuration/configured"
        ),
    )
    check.inst_param(
        configurable,
        "configurable",
        ConfigurableDefinition,
        (
            "Only the following types can be used with the `configured` method: ResourceDefinition, "
            "ExecutorDefinition, CompositeSolidDefinition, SolidDefinition, and LoggerDefinition. "
            "For usage examples of `configured`, see "
            "https://docs.dagster.io/concepts/configuration/configured"
        ),
    )


T_Configurable = TypeVar(
    "T_Configurable", bound=Union["AnonymousConfigurableDefinition", "NamedConfigurableDefinition"]
)


def configured(
    configurable: T_Configurable,
    config_schema: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
) -> Callable[[object], T_Configurable]:
    """
    A decorator that makes it easy to create a function-configured version of an object.
    The following definition types can be configured using this function:

    * :py:class:`GraphDefinition`
    * :py:class:`ExecutorDefinition`
    * :py:class:`LoggerDefinition`
    * :py:class:`ResourceDefinition`
    * :py:class:`OpDefinition`

    Using ``configured`` may result in config values being displayed in Dagit,
    so it is not recommended to use this API with sensitive values, such as
    secrets.

    If the config that will be supplied to the object is constant, you may alternatively invoke this
    and call the result with a dict of config values to be curried. Examples of both strategies
    below.

    Args:
        configurable (ConfigurableDefinition): An object that can be configured.
        config_schema (ConfigSchema): The config schema that the inputs to the decorated function
            must satisfy.
        **kwargs: Arbitrary keyword arguments that will be passed to the initializer of the returned
            object.

    Returns:
        (Callable[[Union[Any, Callable[[Any], Any]]], ConfigurableDefinition])

    **Examples:**

    .. code-block:: python

        dev_s3 = configured(s3_resource, name="dev_s3")({'bucket': 'dev'})

        @configured(s3_resource)
        def dev_s3(_):
            return {'bucket': 'dev'}

        @configured(s3_resource, {'bucket_prefix', str})
        def dev_s3(config):
            return {'bucket': config['bucket_prefix'] + 'dev'}
    """
    _check_configurable_param(configurable)

    if isinstance(configurable, NamedConfigurableDefinition):

        def _configured(config_or_config_fn: object) -> T_Configurable:
            fn_name = (
                getattr(config_or_config_fn, "__name__", None)
                if callable(config_or_config_fn)
                else None
            )
            name: str = check.not_none(kwargs.get("name") or fn_name)
            return configurable.configured(
                config_or_config_fn=config_or_config_fn,
                name=name,  # type: ignore [call-arg] # (mypy bug)
                config_schema=config_schema,
                **{k: v for k, v in kwargs.items() if k != "name"},
            )

        return _configured
    elif isinstance(configurable, AnonymousConfigurableDefinition):

        def _configured(config_or_config_fn: object) -> T_Configurable:
            return configurable.configured(
                config_schema=config_schema, config_or_config_fn=config_or_config_fn, **kwargs
            )

        return _configured
    else:
        check.failed(f"Invalid configurable definition type: {type(configurable)}")
